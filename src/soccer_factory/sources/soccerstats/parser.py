"""Parsers for public SoccerStats daily-index and pre-match preview pages.

The site has distinct page families.  In particular, a daily index can contain both
scheduled ``pmatch.asp`` links and completed ``round_details.asp`` links.  This
module deliberately keeps those states separate.
"""
from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from typing import List, Dict, Optional
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlparse
import re
import uuid

from ..base import BaseParser
from ...schemas.matches import Match
from ...schemas.features import Features

_BASE_URL = "https://www.soccerstats.com/"
_PREVIEW_RE = re.compile(
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{1,2}\s+\w+\s+(\d{4})\s*\|\s*(\d{1,2}:\d{2})\s*UTC",
    re.I,
)


class SoccerStatsParser(BaseParser):
    def __init__(self, version: str = "2.0"):
        self.version = version

    @staticmethod
    def _text(node: Optional[Tag]) -> str:
        return node.get_text(" ", strip=True) if node else ""

    @staticmethod
    def _absolute(href: str) -> str:
        return urljoin(_BASE_URL, href)

    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(value.lower().split())

    @staticmethod
    def _competition_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    def _make_match(
        self, *, competition: str, home: str, away: str, kickoff: datetime,
        time_text: str, status: str, href: str, collected_at: datetime,
        timezone_name: str = "source-unverified",
    ) -> Match:
        country = competition.split(" - ", 1)[0] if " - " in competition else "Unknown"
        canonical = "|".join((
            "match:soccerstats", self._competition_key(competition), kickoff.date().isoformat(),
            time_text, self._normalise(home), self._normalise(away),
        ))
        return Match(
            match_id=str(uuid.uuid5(uuid.NAMESPACE_URL, canonical)),
            sport="soccer", country=country, competition=competition,
            competition_key=self._competition_key(competition), home_team=home,
            away_team=away, normalized_home_team=self._normalise(home),
            normalized_away_team=self._normalise(away), scheduled_kickoff=kickoff,
            timezone=timezone_name, source_urls={"soccerstats": href}, status=status,
            # A source link is strong identity evidence; date/time remains unverified on index pages.
            identity_confidence=1.0 if href else 0.7,
            created_at=collected_at, updated_at=collected_at,
        )

    def parse_matches(self, content: bytes, collected_at: datetime) -> List[Match]:  # type: ignore[override]
        soup = BeautifulSoup(content, "lxml")
        # Retain support for the repository's original fixtures.
        legacy = soup.find("table", id="btable")
        if legacy:
            return self._parse_legacy_index(legacy, collected_at)
        return self._parse_live_index(soup, collected_at)

    def _parse_legacy_index(self, table: Tag, collected_at: datetime) -> List[Match]:
        matches: List[Match] = []
        competition = "Unknown"
        for row in table.find_all("tr"):
            classes = row.get("class") or []
            if "trow3" in classes:
                cell = row.find("td")
                if cell and cell.b:
                    competition = self._text(cell.b)
                continue
            if "trow8" not in classes:
                continue
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            display_time, home, away = self._text(cells[0]), self._text(cells[1]), self._text(cells[3])
            anchor = cells[4].find("a", href=True)
            # Existing fixture tests use relative source URLs; preserve those legacy values.
            href = str(anchor["href"]) if anchor else ""
            status = "postponed" if "P-P" in display_time else "live" if ("'" in display_time or display_time == "HT") else "finished" if display_time == "FT" else "pre-match"
            kickoff = collected_at
            if status == "pre-match" and re.fullmatch(r"\d{1,2}:\d{2}", display_time):
                hour, minute = map(int, display_time.split(":"))
                kickoff = collected_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
            matches.append(self._make_match(competition=competition, home=home, away=away,
                kickoff=kickoff, time_text=display_time, status=status, href=href,
                collected_at=collected_at, timezone_name="UTC"))
        return matches

    def _parse_live_index(self, soup: BeautifulSoup, collected_at: datetime) -> List[Match]:
        """Parse current index markup: a `parent` league row plus team1row/team2row pairs."""
        matches: List[Match] = []
        competition = "Unknown"
        # A numeric score on the current-day page can be live. On an explicitly
        # labelled yesterday/results index, the same two-score layout is final.
        page_title = self._text(soup.title).lower()
        is_yesterday_results = "yesterday" in page_title and "result" in page_title
        # Only direct rows are processed: nested tables otherwise cause duplicate rows.
        for row in soup.select("tr"):
            classes = set(row.get("class") or [])
            if "parent" in classes:
                label = self._text(row.find("td"))
                # The heading includes a trailing 'stats' link; strip just that display suffix.
                competition = re.sub(r"\s+stats\s*$", "", label, flags=re.I)
                continue
            if "team1row" not in classes:
                continue
            next_row = row.find_next_sibling("tr", class_="team2row")
            cells, away_cells = row.find_all("td", recursive=False), (next_row.find_all("td", recursive=False) if next_row else [])
            if not cells or not away_cells:
                continue
            home, away = self._text(cells[0]), self._text(away_cells[0])
            if not home or not away:
                continue
            marker = self._text(cells[1]) if len(cells) > 1 else ""
            anchor = row.find("a", href=True)
            href = self._absolute(str(anchor["href"])) if anchor else ""
            path = urlparse(href).path.lower()
            away_marker = self._text(away_cells[1]) if len(away_cells) > 1 else ""
            has_score_pair = bool(re.fullmatch(r"\d+", marker) and re.fullmatch(r"\d+", away_marker))
            if "round_details.asp" in path:
                status = "finished"
            elif is_yesterday_results and has_score_pair:
                status = "finished"
            elif marker.lower() in {"pp.", "p-p"}:
                status = "postponed"
            elif re.fullmatch(r"\d{1,2}:\d{2}", marker):
                status = "pre-match"
            elif re.search(r"\b(?:ht|ft|\d{1,2}'?)\b", marker, re.I):
                status = "live" if marker.upper() != "FT" else "finished"
            else:
                status = "unknown"
            # Index time has no explicit timezone; retain its wall-clock value without labelling UTC.
            kickoff = collected_at
            if re.fullmatch(r"\d{1,2}:\d{2}", marker):
                hour, minute = map(int, marker.split(":"))
                kickoff = collected_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
            matches.append(self._make_match(competition=competition, home=home, away=away,
                kickoff=kickoff, time_text=marker, status=status, href=href,
                collected_at=collected_at))
        return matches

    @staticmethod
    def _number(value: str) -> Optional[float]:
        value = value.strip().replace("%", "")
        try:
            return float(value)
        except ValueError:
            return None

    def _preview_kickoff(self, soup: BeautifulSoup, fallback: datetime) -> datetime:
        match = _PREVIEW_RE.search(soup.get_text(" ", strip=True))
        if not match:
            return fallback
        # The year/time are explicit but the abbreviated day/month must be read from the full match.
        full = match.group(0)
        try:
            return datetime.strptime(full, "%a %d %b %Y | %H:%M UTC").replace(tzinfo=timezone.utc)
        except ValueError:
            return fallback

    def _goal_rates(self, soup: BeautifulSoup) -> tuple[Dict[str, float], Dict[str, float]]:
        """Extract labelled Total goal/BTTS rates from the preview comparison.

        SoccerStats renders the home and away values in one row, so table
        position is deliberately not used. The repeated ``Total`` labels are
        the stable semantic anchors.
        """
        for table in soup.find_all("table"):
            table_text = self._text(table)
            if not all(label in table_text for label in ("1.5+", "2.5+", "3.5+", "BTS")):
                continue
            for row in table.find_all("tr"):
                values = [self._text(cell) for cell in row.find_all(["td", "th"], recursive=False)]
                total_positions = [i for i, value in enumerate(values) if value.lower() == "total"]
                if len(total_positions) != 2:
                    continue
                left, right = total_positions
                # After each Total label: 1.5+, 2.5+, 3.5+, TG, BTS.
                if right - left < 6 or len(values) < right + 6:
                    continue
                home_values = [self._number(value) for value in values[left + 1:left + 6]]
                away_values = [self._number(value) for value in values[right + 1:right + 6]]
                if any(value is None for value in home_values + away_values):
                    continue
                return (
                    dict(zip(("over_15", "over_25", "over_35", "tg", "btts"), home_values)),
                    dict(zip(("over_15", "over_25", "over_35", "tg", "btts"), away_values)),
                )
        return {}, {}

    def parse_features(self, content: bytes, match_id: str, collected_at: datetime) -> List[Features]:
        soup = BeautifulSoup(content, "lxml")
        explicit_kickoff = _PREVIEW_RE.search(soup.get_text(" ", strip=True))
        kickoff = self._preview_kickoff(soup, collected_at)
        # Explicitly refuse a post-kickoff snapshot only when the preview itself
        # supplied a real UTC kickoff. Legacy fixtures deliberately omit it.
        if explicit_kickoff and kickoff.tzinfo and collected_at.tzinfo and collected_at >= kickoff:
            return []

        # Live preview comparison table has a P/W/D/L/GF/GA header and two data rows.
        for table in soup.find_all("table"):
            rows = table.find_all("tr", recursive=False)
            if len(rows) < 3:
                continue
            # Live markup uses empty spacer cells; remove them before checking
            # the semantic column sequence.
            header = [self._text(x) for x in rows[0].find_all(["td", "th"], recursive=False)]
            header = [value for value in header if value]
            if header[:7] != ["P", "W", "D", "L", "GF", "GA", "W%"]:
                continue
            data_rows = rows[1:3]
            parsed: list[Dict[str, float]] = []
            for r in data_rows:
                vals = [self._text(x) for x in r.find_all(["td", "th"], recursive=False)]
                vals = [value for value in vals if value]
                # first value is a side label, then P W D L GF GA W% D% L% Avg GF Avg GA PPG
                if len(vals) < 14:
                    break
                nums = [self._number(v) for v in vals[1:]]
                if any(v is None for v in nums):
                    break
                parsed.append(dict(zip(["gp", "w", "d", "l", "gf", "ga", "win_pct", "draw_pct", "loss_pct", "avg_gf", "avg_ga", "avg_tg", "ppg"], nums)))
            if len(parsed) != 2:
                continue
            # BTTS and O2.5 are available elsewhere on the preview but intentionally omitted
            # until the labelled total-goals table gets its own stable extractor.
            home, away = parsed
            home_rates, away_rates = self._goal_rates(soup)
            return [Features(match_id=match_id, collected_at=collected_at,
                feature_cutoff=collected_at, match_kickoff=kickoff, data_type="pre-match",
                source_status="pre-match", home_goals_scored_avg=home["avg_gf"],
                home_goals_conceded_avg=home["avg_ga"], away_goals_scored_avg=away["avg_gf"],
                away_goals_conceded_avg=away["avg_ga"], home_ppg=home["ppg"],
                away_ppg=away["ppg"], sample_size_home=int(home["gp"]),
                sample_size_away=int(away["gp"]), home_total_goals_avg=home_rates.get("tg") if home_rates else None,
                away_total_goals_avg=away_rates.get("tg") if away_rates else None,
                btts_rate_home=home_rates.get("btts", 0.0) / 100.0 if home_rates else None,
                btts_rate_away=away_rates.get("btts", 0.0) / 100.0 if away_rates else None,
                over_15_rate_home=home_rates.get("over_15", 0.0) / 100.0 if home_rates else None,
                over_15_rate_away=away_rates.get("over_15", 0.0) / 100.0 if away_rates else None,
                over_25_rate_home=home_rates.get("over_25", 0.0) / 100.0 if home_rates else None,
                over_25_rate_away=away_rates.get("over_25", 0.0) / 100.0 if away_rates else None,
                over_35_rate_home=home_rates.get("over_35", 0.0) / 100.0 if home_rates else None,
                over_35_rate_away=away_rates.get("over_35", 0.0) / 100.0 if away_rates else None)]
        return self._parse_legacy_features(soup, match_id, collected_at)

    def _parse_legacy_features(self, soup: BeautifulSoup, match_id: str, collected_at: datetime) -> List[Features]:
        tables = soup.find_all("table", class_="sortable")
        if len(tables) < 2:
            return []
        def extract(table: Tag) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) == 2:
                    value = self._number(self._text(cells[1]))
                    if value is not None:
                        out[self._text(cells[0])] = value
            return out
        home, away = extract(tables[0]), extract(tables[1])
        if not home or not away:
            return []
        return [Features(match_id=match_id, collected_at=collected_at, feature_cutoff=collected_at,
            match_kickoff=collected_at, data_type="pre-match", source_status="pre-match",
            home_goals_scored_avg=home.get("GF"), home_goals_conceded_avg=home.get("GA"),
            away_goals_scored_avg=away.get("GF"), away_goals_conceded_avg=away.get("GA"),
            btts_rate_home=(home.get("BTS", 0.0) / 100.0), btts_rate_away=(away.get("BTS", 0.0) / 100.0),
            over_25_rate_home=(home.get("2.5+", 0.0) / 100.0), over_25_rate_away=(away.get("2.5+", 0.0) / 100.0),
            home_ppg=home.get("PPG"), away_ppg=away.get("PPG"),
            sample_size_home=int(home.get("GP", 0.0)), sample_size_away=int(away.get("GP", 0.0))) ]

    def parse_predictions(self, content: bytes, collected_at: datetime) -> list[object]:
        return []

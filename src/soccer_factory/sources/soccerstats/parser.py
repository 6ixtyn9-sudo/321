"""Parsers for public SoccerStats daily-index and pre-match preview pages.

The site has distinct page families.  In particular, a daily index can contain both
scheduled ``pmatch.asp`` links and completed ``round_details.asp`` links.  This
module deliberately keeps those states separate.

PATCHED VERSION:
- Adds support for "by-time" view (matchday=6,106,206) which is NOT limited to 10 matches.
- Adds support for league latest pages (latest.asp?league=...) to bypass the 10-match public limit.
- Detects the "ONLY LISTING A MAXIMUM OF 10 MATCHES" truncation banner.
- Merges matches from multiple scopes with de-duplication.
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
# Date pattern for by-time view: Thu 23 Jul 01:00
_BYTIME_DATE_RE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{1,2}\s+\w+\s+\d{2}:\d{2}$")
# Country code pattern 2-3 uppercase letters, INT for international
_COUNTRY_RE = re.compile(r"^[A-Z]{2,3}$")


class SoccerStatsParser(BaseParser):
    def __init__(self, version: str = "2.1-patched"):
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
        # Stable canonical: exclude raw time_text which varies between grouped (23:30) and by-time (Thu 23 Jul 23:30)
        # Use only date + normalized teams + competition
        canonical = "|".join((
            "match:soccerstats", self._competition_key(competition), kickoff.date().isoformat(),
            self._normalise(home), self._normalise(away),
        ))
        return Match(
            match_id=str(uuid.uuid5(uuid.NAMESPACE_URL, canonical)),
            sport="soccer", country=country, competition=competition,
            competition_key=self._competition_key(competition), home_team=home,
            away_team=away, normalized_home_team=self._normalise(home),
            normalized_away_team=self._normalise(away), scheduled_kickoff=kickoff,
            timezone=timezone_name, source_urls={"soccerstats": href}, status=status,
            identity_confidence=1.0 if href else 0.7,
            created_at=collected_at, updated_at=collected_at,
        )

    def parse_matches(self, content: bytes, collected_at: datetime) -> List[Match]:
        soup = BeautifulSoup(content, "lxml")
        # Detect 10-match truncation banner - still parse what we have
        # Retain support for the repository's original fixtures, but only if it actually contains matches
        legacy = soup.find("table", id="btable")
        if legacy:
            legacy_matches = self._parse_legacy_index(legacy, collected_at)
            if legacy_matches:
                return legacy_matches
            # If legacy table exists but yields nothing (e.g., navigation table on latest page),
            # continue to other parsers

        # Try latest league page FIRST - it has microdata SportsEvent which is most structured
        # and also contains btable navigation that would otherwise mislead legacy check
        # Heuristic: contains many pmatch links and SportsEvent microdata
        if soup.find_all("div", itemtype="https://schema.org/SportsEvent"):
            latest = self._parse_latest_league_page(soup, collected_at)
            if latest:
                return latest

        # Try by-time view (matchday=6,106,206) - it has no parent/team1row
        # Heuristic: page contains "DateCountryHome teamAway team" and date pattern rows
        text = soup.get_text()
        if "DateCountryHome teamAway team" in text.replace(" ", "").replace("\n", "") or \
           "matches by time" in self._text(soup.title).lower():
            bytime = self._parse_bytime_index(soup, collected_at)
            if bytime:
                return bytime

        # Fallback: check if any row matches by-time date pattern, even if title doesn't
        has_bytime_rows = False
        for tr in soup.select("tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) >= 3:
                dtxt = self._text(cells[0])
                if _BYTIME_DATE_RE.match(dtxt):
                    has_bytime_rows = True
                    break
        if has_bytime_rows:
            bytime = self._parse_bytime_index(soup, collected_at)
            if bytime:
                return bytime

        # Try latest league page (latest.asp?league=...) via heuristic
        if soup.find_all("a", href=lambda x: x and "pmatch.asp" in x):
            # Check if it looks like latest page structure
            if any("Home / Away" in self._text(t) for t in soup.find_all("tr")):
                latest = self._parse_latest_league_page(soup, collected_at)
                if latest:
                    return latest

        # Default: grouped by league view (parent/team1row)
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
        page_title = self._text(soup.title).lower()
        is_yesterday_results = "yesterday" in page_title and "result" in page_title
        for row in soup.select("tr"):
            classes = set(row.get("class") or [])
            if "parent" in classes:
                label = self._text(row.find("td"))
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
            kickoff = collected_at
            if re.fullmatch(r"\d{1,2}:\d{2}", marker):
                hour, minute = map(int, marker.split(":"))
                kickoff = collected_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
            matches.append(self._make_match(competition=competition, home=home, away=away,
                kickoff=kickoff, time_text=marker, status=status, href=href,
                collected_at=collected_at))
        return matches

    def _parse_bytime_index(self, soup: BeautifulSoup, collected_at: datetime) -> List[Match]:
        """
        Parse the 'by time' view (matchday=6,106,206) which is NOT limited to 10 matches.
        Structure:
        <tr>
          <td>Thu 23 Jul 01:00</td>
          <td><flag></td>
          <td>ECU</td>
          <td>Manta</td>
          <td>1:1</td>
          <td>LDU Quito</td>
          <td><a href=round_details...></td>
          <td></td>
          <td><a href=latest.asp?league=ecuador>League stats</a></td>
        </tr>
        """
        matches: List[Match] = []
        # Find all rows that look like match rows
        for row in soup.select("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 5:
                continue
            date_text = self._text(cells[0])
            if not _BYTIME_DATE_RE.match(date_text):
                continue

            # Heuristic to locate country, home, score, away
            # Country is usually a 2-3 letter uppercase code in one of the cells
            country_code = None
            country_idx = None
            for idx, cell in enumerate(cells):
                txt = self._text(cell)
                if _COUNTRY_RE.fullmatch(txt):
                    # Avoid matching "USA" etc inside other contexts, but okay
                    # Also ensure it's not too far from start
                    if idx <= 4:
                        country_code = txt
                        country_idx = idx
                        break
            if country_idx is None:
                # Fallback: assume cell[2] is country
                country_idx = 2
                country_code = self._text(cells[2]) if len(cells) > 2 else "UNK"

            # Home, score, away are relative to country
            try:
                home_cell = cells[country_idx + 1]
                score_cell = cells[country_idx + 2]
                away_cell = cells[country_idx + 3]
            except IndexError:
                continue

            home = self._text(home_cell)
            score_text = self._text(score_cell)
            away = self._text(away_cell)

            if not home or not away:
                continue

            # Extract links from row
            anchors = row.find_all("a", href=True)
            detail_href = ""
            league_slug = ""
            competition = country_code  # default
            for a in anchors:
                href = str(a["href"])
                if any(token in href for token in ("round_details.asp", "pmatch.asp", "h2h.asp", "leagueview_team.asp")):
                    if not detail_href:
                        detail_href = self._absolute(href)
                if "latest.asp" in href and "league=" in href:
                    # parse league param
                    try:
                        qs = parse_qs(urlparse(href).query)
                        league_param = qs.get("league", [""])[0]
                        if league_param:
                            league_slug = league_param
                            # competition as "COUNTRY - league" if we can
                            # Use league_slug as competition, but keep country separate
                            competition = f"{country_code} - {league_slug}" if country_code else league_slug
                    except:
                        pass

            # If no league slug found, competition stays as country_code
            # Status detection
            if "round_details.asp" in detail_href:
                status = "finished"
            elif score_text == "-" or score_text == "" or score_text.lower() == "v":
                status = "pre-match"
            elif re.fullmatch(r"\d+\s*:\s*\d+", score_text):
                # Score present, could be finished
                # Check if row also has h2h => pre-match? Actually finished rows have score and round_details
                # Pre-match rows have "-" and h2h/pmatch
                # So if score is "-": pre-match, else if score like "1:1" and link is round_details => finished
                # For safety, if link contains h2h or pmatch and score is "-", pre-match, else finished
                if any(x in detail_href for x in ("h2h.asp", "pmatch.asp")):
                    # pmatch with "-" is pre-match, but with score? Could be live?
                    status = "pre-match" if score_text.strip() == "-" else "finished"
                else:
                    status = "finished"
            elif re.search(r"\d+'", score_text):
                status = "live"
            else:
                status = "unknown"

            # Kickoff parsing: date_text like "Thu 23 Jul 01:00"
            kickoff = collected_at
            try:
                # Add year from collected_at
                dt_str = f"{date_text} {collected_at.year}"
                # Try parsing "%a %d %b %H:%M %Y"
                dt = datetime.strptime(dt_str, "%a %d %b %H:%M %Y")
                kickoff = dt.replace(tzinfo=timezone.utc)
            except Exception:
                # Fallback: try without day name
                try:
                    # Remove day name
                    parts = date_text.split()
                    # parts = ['Thu', '23', 'Jul', '01:00'] -> "23 Jul 01:00 2026"
                    if len(parts) >= 4:
                        dt_str2 = f"{parts[1]} {parts[2]} {parts[3]} {collected_at.year}"
                        dt = datetime.strptime(dt_str2, "%d %b %H:%M %Y")
                        kickoff = dt.replace(tzinfo=timezone.utc, year=collected_at.year)
                except Exception:
                    kickoff = collected_at

            matches.append(self._make_match(
                competition=competition or "Unknown",
                home=home,
                away=away,
                kickoff=kickoff,
                time_text=date_text,
                status=status,
                href=detail_href,
                collected_at=collected_at
            ))
        return matches

    def _parse_latest_league_page(self, soup: BeautifulSoup, collected_at: datetime) -> List[Match]:
        """
        Parse latest.asp?league=... pages which list upcoming and past matches for a single league.

        Primary method: Use schema.org SportsEvent microdata (div itemtype SportsEvent)
        which is present in latest pages and contains structured home/away and date.

        Fallback: Old heuristic with home/away labels.
        """
        matches: List[Match] = []
        # Competition from title
        page_title = self._text(soup.title)
        competition = "Unknown"
        if " - " in page_title:
            competition = page_title.split(" table")[0].split(" |")[0].strip()
        else:
            competition = page_title

        # PRIMARY: Microdata SportsEvent
        events = soup.find_all("div", itemtype="https://schema.org/SportsEvent")
        if events:
            for ev in events:
                # Extract home, away from itemprop
                # The spans have content attribute with team names
                home = ""
                away = ""
                # Try to get from meta content
                home_span = ev.find("span", itemprop="homeTeam")
                if home_span:
                    inner = home_span.find("span", itemprop="name")
                    if inner and inner.get("content"):
                        home = inner.get("content")
                    else:
                        home = self._text(home_span)
                away_span = ev.find("span", itemprop="awayTeam")
                if away_span:
                    inner = away_span.find("span", itemprop="name")
                    if inner and inner.get("content"):
                        away = inner.get("content")
                    else:
                        away = self._text(away_span)

                # Fallback: parse name "Botafogo vs Vitoria"
                if not home or not away:
                    name_span = ev.find("span", itemprop="name")
                    if name_span:
                        name_content = name_span.get("content") or self._text(name_span)
                        if " vs " in name_content:
                            parts = name_content.split(" vs ")
                            if len(parts) == 2:
                                home = home or parts[0].strip()
                                away = away or parts[1].strip()

                if not home or not away:
                    continue

                # Date
                date_tag = ev.find("time", itemprop="startDate")
                date_str = date_tag.get("datetime") if date_tag and date_tag.get("datetime") else ""
                kickoff = collected_at
                time_text = date_str
                if date_str:
                    try:
                        # date_str like "2026-07-23" or "2026-07-23T23:30" ?
                        # Try parsing ISO
                        if "T" in date_str:
                            kickoff = datetime.fromisoformat(date_str)
                            if kickoff.tzinfo is None:
                                kickoff = kickoff.replace(tzinfo=timezone.utc)
                        else:
                            # Just date, assume midnight
                            kickoff = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            kickoff = kickoff.replace(hour=0, minute=0)
                        time_text = date_str
                    except Exception:
                        kickoff = collected_at

                # Detail href
                detail_href = ""
                a_tag = ev.find("a", itemprop="url")
                if a_tag and a_tag.get("href"):
                    detail_href = self._absolute(str(a_tag["href"]))

                status = "finished" if "round_details.asp" in detail_href else "pre-match"
                # If the event page also has a final score nearby, we could detect finished,
                # but for latest pages future matches are pre-match

                matches.append(self._make_match(
                    competition=competition,
                    home=home,
                    away=away,
                    kickoff=kickoff,
                    time_text=time_text,
                    status=status,
                    href=detail_href,
                    collected_at=collected_at
                ))
            if matches:
                return matches

        # FALLBACK: Old heuristic with home/away labels
        rows = soup.select("tr")
        i = 0
        while i < len(rows):
            row = rows[i]
            cells = row.find_all("td", recursive=False)
            if not cells:
                i += 1
                continue
            date_cell_text = ""
            for cell in cells:
                txt = self._text(cell)
                if re.search(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Th|Tu|We)\s+\d{1,2}\s+\w+", txt):
                    date_cell_text = txt
                    break
            if not date_cell_text:
                i += 1
                continue

            time_match = re.search(r"(\d{1,2}:\d{2})", date_cell_text)
            time_text = time_match.group(1) if time_match else date_cell_text

            home = ""
            for idx, cell in enumerate(cells):
                txt = self._text(cell).lower()
                if txt == "home":
                    if idx + 1 < len(cells):
                        home = self._text(cells[idx + 1])
                    break
            if not home and len(cells) >= 4:
                home = self._text(cells[3])

            away = ""
            detail_href = ""
            if i + 1 < len(rows):
                next_row = rows[i + 1]
                next_cells = next_row.find_all("td", recursive=False)
                for idx, cell in enumerate(next_cells):
                    txt = self._text(cell).lower()
                    if txt == "away":
                        if idx + 1 < len(next_cells):
                            away = self._text(next_cells[idx + 1])
                        break
                for r in (row, next_row):
                    a = r.find("a", href=lambda x: x and "pmatch.asp" in x)
                    if a and a.get("href"):
                        detail_href = self._absolute(str(a["href"]))
                        break
                    a = r.find("a", href=lambda x: x and "round_details.asp" in x)
                    if a and a.get("href"):
                        detail_href = self._absolute(str(a["href"]))
                        break

            if home and away:
                status = "finished" if "round_details.asp" in detail_href else "pre-match"
                kickoff = collected_at
                if time_match:
                    try:
                        hour, minute = map(int, time_match.group(1).split(":"))
                        kickoff = collected_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    except:
                        kickoff = collected_at

                matches.append(self._make_match(
                    competition=competition,
                    home=home,
                    away=away,
                    kickoff=kickoff,
                    time_text=time_text,
                    status=status,
                    href=detail_href,
                    collected_at=collected_at
                ))
                i += 2
            else:
                i += 1
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
        full = match.group(0)
        try:
            return datetime.strptime(full, "%a %d %b %Y | %H:%M UTC").replace(tzinfo=timezone.utc)
        except ValueError:
            return fallback

    def _goal_rates(self, soup: BeautifulSoup) -> tuple[Dict[str, float], Dict[str, float]]:
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
        if explicit_kickoff and kickoff.tzinfo and collected_at.tzinfo and collected_at >= kickoff:
            return []

        for table in soup.find_all("table"):
            rows = table.find_all("tr", recursive=False)
            if len(rows) < 3:
                continue
            header = [self._text(x) for x in rows[0].find_all(["td", "th"], recursive=False)]
            header = [value for value in header if value]
            if header[:7] != ["P", "W", "D", "L", "GF", "GA", "W%"]:
                continue
            data_rows = rows[1:3]
            parsed: list[Dict[str, float]] = []
            for r in data_rows:
                vals = [self._text(x) for x in r.find_all(["td", "th"], recursive=False)]
                vals = [value for value in vals if value]
                if len(vals) < 14:
                    break
                nums = [self._number(v) for v in vals[1:]]
                if any(v is None for v in nums):
                    break
                parsed.append(dict(zip(["gp", "w", "d", "l", "gf", "ga", "win_pct", "draw_pct", "loss_pct", "avg_gf", "avg_ga", "avg_tg", "ppg"], nums)))
            if len(parsed) != 2:
                continue
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
        alternate = self._parse_scoring_layout(soup, match_id, collected_at, kickoff)
        if alternate:
            return alternate
        return self._parse_legacy_features(soup, match_id, collected_at)

    def _parse_scoring_layout(self, soup: BeautifulSoup, match_id: str, collected_at: datetime,
                              kickoff: datetime) -> List[Features]:
        scoring_tables = []
        for table in soup.find_all("table"):
            header = " ".join(table.find("tr").stripped_strings) if table.find("tr") else ""
            if header.strip().upper() == "SCORING HOME AWAY ALL":
                rows: Dict[str, tuple[Optional[float], Optional[float]]] = {}
                for row in table.find_all("tr"):
                    cells = [self._text(cell) for cell in row.find_all("td", recursive=False)]
                    if len(cells) >= 3:
                        label = " ".join(cells[0].split()).lower()
                        rows[label] = (self._number(cells[1]), self._number(cells[2]))
                scoring_tables.append(rows)
        if len(scoring_tables) < 2:
            return []

        def value(table: Dict[str, tuple[Optional[float], Optional[float]]], label: str, side: int) -> Optional[float]:
            pair = table.get(label.lower())
            return pair[side] if pair else None

        home_table, away_table = scoring_tables[0], scoring_tables[1]
        ppg_pairs: list[Optional[float]] = []
        for row in soup.find_all("tr"):
            cells = [self._text(cell) for cell in row.find_all("td", recursive=False)]
            if len(cells) == 2 and "points per game at home" in cells[0].lower():
                ppg_pairs.append(self._number(cells[1]))
            elif len(cells) == 2 and "points per game away" in cells[0].lower():
                ppg_pairs.append(self._number(cells[1]))
        home_ppg = ppg_pairs[0] if len(ppg_pairs) >= 1 else None
        away_ppg = ppg_pairs[3] if len(ppg_pairs) >= 4 else None

        home_gf = value(home_table, "gf per match", 0)
        away_gf = value(away_table, "gf per match", 1)
        home_ga = value(home_table, "ga per match", 0)
        away_ga = value(away_table, "ga per match", 1)
        if None in (home_gf, away_gf, home_ga, away_ga):
            return []
        pct = lambda table, label, side: (value(table, label, side) / 100.0) if value(table, label, side) is not None else None
        return [Features(match_id=match_id, collected_at=collected_at, feature_cutoff=collected_at,
            match_kickoff=kickoff, data_type="pre-match", source_status="pre-match",
            home_goals_scored_avg=home_gf, away_goals_scored_avg=away_gf,
            home_goals_conceded_avg=home_ga, away_goals_conceded_avg=away_ga,
            home_total_goals_avg=value(home_table, "gf + ga per match", 0),
            away_total_goals_avg=value(away_table, "gf + ga per match", 1),
            over_15_rate_home=pct(home_table, "gf+ga over 1.5", 0),
            over_15_rate_away=pct(away_table, "gf+ga over 1.5", 1),
            over_25_rate_home=pct(home_table, "gf+ga over 2.5", 0),
            over_25_rate_away=pct(away_table, "gf+ga over 2.5", 1),
            over_35_rate_home=pct(home_table, "gf+ga over 3.5", 0),
            over_35_rate_away=pct(away_table, "gf+ga over 3.5", 1),
            home_ppg=home_ppg, away_ppg=away_ppg)]

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

    def parse_index_features(self, content: bytes, collected_at: datetime, feature_scope: str = "home_away") -> List[Features]:
        soup = BeautifulSoup(content, "lxml")
        if soup.find("table", id="btable"):
            return []
        matches = self._parse_live_index(soup, collected_at)
        # Also try by-time for feature scope? By-time has no stats, so skip
        if not matches:
            matches = self._parse_bytime_index(soup, collected_at)
        by_pair = {(m.home_team, m.away_team): m for m in matches if m.status == "pre-match"}
        features: List[Features] = []
        for row in soup.select("tr.team1row"):
            away_row = row.find_next_sibling("tr", class_="team2row")
            home_cells = row.find_all("td", recursive=False)
            away_cells = away_row.find_all("td", recursive=False) if away_row else []
            if not home_cells or not away_cells:
                continue
            home, away = self._text(home_cells[0]), self._text(away_cells[0])
            match = by_pair.get((home, away))
            if not match:
                continue

            def metrics(cells: list[Tag]) -> Optional[Dict[str, float]]:
                values = [self._text(cell) for cell in cells]
                try:
                    scope_at = next(i for i, value in enumerate(values) if value.lower() in {"home", "away", "total", "last 8"})
                except StopIteration:
                    return None
                raw = [value for value in values[scope_at + 1:] if value][:12]
                if len(raw) != 12:
                    return None
                numbers = [self._number(value) for value in raw]
                if any(value is None for value in numbers):
                    return None
                return dict(zip(("gp", "win", "fts", "cs", "btts", "tg", "gf", "ga", "over15", "over25", "over35", "ppg"), numbers))

            home_metrics, away_metrics = metrics(home_cells), metrics(away_cells)
            if not home_metrics or not away_metrics:
                continue
            features.append(Features(
                match_id=match.match_id, collected_at=collected_at, feature_cutoff=collected_at,
                match_kickoff=match.scheduled_kickoff, data_type="pre-match", source_status="pre-match", feature_scope=feature_scope,
                home_ppg=home_metrics["ppg"], away_ppg=away_metrics["ppg"],
                home_win_rate=home_metrics["win"] / 100.0, away_win_rate=away_metrics["win"] / 100.0,
                home_failed_to_score_rate=home_metrics["fts"] / 100.0, away_failed_to_score_rate=away_metrics["fts"] / 100.0,
                home_clean_sheet_rate=home_metrics["cs"] / 100.0, away_clean_sheet_rate=away_metrics["cs"] / 100.0,
                btts_rate_home=home_metrics["btts"] / 100.0, btts_rate_away=away_metrics["btts"] / 100.0,
                home_total_goals_avg=home_metrics["tg"], away_total_goals_avg=away_metrics["tg"],
                home_goals_scored_avg=home_metrics["gf"], away_goals_scored_avg=away_metrics["gf"],
                home_goals_conceded_avg=home_metrics["ga"], away_goals_conceded_avg=away_metrics["ga"],
                over_15_rate_home=home_metrics["over15"] / 100.0, over_15_rate_away=away_metrics["over15"] / 100.0,
                over_25_rate_home=home_metrics["over25"] / 100.0, over_25_rate_away=away_metrics["over25"] / 100.0,
                over_35_rate_home=home_metrics["over35"] / 100.0, over_35_rate_away=away_metrics["over35"] / 100.0,
                sample_size_home=int(home_metrics["gp"]), sample_size_away=int(away_metrics["gp"]),
            ))
        return features

    def detect_pmatch_state(self, content: bytes) -> str:
        text = content.decode('utf-8', errors='ignore').lower()
        if 'full-time' in text or 'ft' in text and 'final' in text:
            return 'finished_post_match'
        if re.search(r'final score[:\s]*\d+[-:]\d+', text):
            return 'finished_post_match'
        if ('ht ' in text or 'ht:' in text or 'in play' in text or 'live score' in text) and 'pre-match' not in text:
            return 'live'
        if re.search(r'\d{1,2}[\':]\d{2}', text) and ('pre-match' in text or 'scheduled' in text):
            return 'pre_match'
        if 'pre-match' in text or 'points per game' in text or 'scoring home away all' in text:
            return 'pre_match'
        return 'unknown'

    def parse_predictions(self, content: bytes, collected_at: datetime) -> list[object]:
        return []

    # ------------------------------------------------------------------
    # NEW HELPERS FOR PATCHED VERSION
    # ------------------------------------------------------------------
    def is_truncated_by_member_limit(self, content: bytes) -> bool:
        """Detect the public 10-match limit banner."""
        return b"MAXIMUM OF 10 MATCHES" in content or b"Only listing a maximum of 10 matches" in content

    def parse_all_with_dedup(self, contents: List[bytes], collected_at: datetime) -> List[Match]:
        """Parse multiple index pages and deduplicate by match_id."""
        seen = {}
        for content in contents:
            for m in self.parse_matches(content, collected_at):
                seen[m.match_id] = m
        return list(seen.values())

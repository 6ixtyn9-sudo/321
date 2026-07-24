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
    def __init__(self, version: str = "2.2-expanded-ms"):
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

    # ------------------------------------------------------------------
    # Expanded layout detection / iteration
    # ------------------------------------------------------------------
    @staticmethod
    def _is_metric_header_row(row: Tag) -> bool:
        """Return True if the row is the per-league 'Scope GP W% FTS CS ...' header
        nested inside a <table> (expanded ms= layout)."""
        cells = row.find_all("td", recursive=False)
        text_cells = [SoccerStatsParser._text(c) for c in cells]
        return "Scope" in text_cells and "GP" in text_cells and "BTS" in text_cells

    @staticmethod
    def _row_team_anchor(row: Tag) -> Optional[Tag]:
        """Return the match-detail anchor in a match row (if any).

        In compact layout it's the 'stats' / 'analysis' link inside the home row.
        In expanded layout the same anchor is present (rowspan=2, 'stats' label) in
        the home row only.
        """
        for a in row.find_all("a", href=True):
            href = a.get("href", "")
            if any(token in href for token in ("pmatch.asp", "round_details.asp", "leagueview_team.asp", "h2h.asp")):
                return a
        return None

    @staticmethod
    def _is_expanded_home_row(row: Tag) -> bool:
        """Return True if this is the HOME row in the expanded vertical layout.

        Heuristic: first <td> is class 'steam' (team name), and there exists a <td>
        with rowspan='2' (either the kickoff marker OR the stats button), AND the
        team-name cell does NOT itself have rowspan=2 (away rows have class 'steam'
        but no rowspan=2 sibling on the stats button because that button spans
        across both rows and thus only appears in the home row).
        """
        cells = row.find_all("td", recursive=False)
        if not cells:
            return False
        # Row must NOT be a parent/child (metric header)
        classes = set(row.get("class") or [])
        if "parent" in classes or "child" in classes:
            return False
        first = cells[0]
        if "steam" not in (first.get("class") or []):
            return False
        # Must have a rowspan=2 td somewhere (time cell or stats button)
        for td in cells:
            if td.get("rowspan") == "2":
                return True
        return False

    def _classify_marker(self, marker: str, href: str, is_yesterday_results: bool,
                         has_bold_scores: bool = False) -> tuple[str, datetime]:
        """Turn a kickoff/score marker text into (status, kickoff).

        ``has_bold_scores`` indicates the row uses ``<b>1</b>``/``<b>4</b>`` score
        cells rather than a plain "2 - 1" marker string (seen on today/tomorrow
        pages for matches in progress); those are treated as live rather than
        automatically finished.
        """
        path = urlparse(href).path.lower() if href else ""
        marker = (marker or "").strip()
        if "round_details.asp" in path:
            return "finished", self._collected
        if marker.lower() in {"pp.", "p-p", "pp"}:
            return "postponed", self._collected
        if re.fullmatch(r"\d{1,2}:\d{2}", marker):
            hour, minute = map(int, marker.split(":"))
            kickoff = self._collected.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return "pre-match", kickoff
        # Score pair e.g. "2 - 1", "2:1", "2-1"
        if re.fullmatch(r"\d+\s*[-:]\s*\d+", marker):
            if is_yesterday_results:
                return "finished", self._collected
            # On today/tomorrow pages, a numeric score pair without a round_details
            # link is a live/in-progress score (pmatch "stats" anchor still present).
            if "pmatch.asp" in path or not path:
                return "live", self._collected
            return "finished", self._collected
        # Bold score cells (compact layout uses <b>1</b>/<b>4</b> for live scores)
        if has_bold_scores and not is_yesterday_results:
            return "live", self._collected
        if re.search(r"\b(?:ht|ft|\d{1,2}'?)\b", marker, re.I):
            return "live" if marker.upper() != "FT" else "finished", self._collected
        return "unknown", self._collected

    def _iter_index_rows(self, soup: BeautifulSoup):
        """Yield <tr> rows belonging to the daily index, skipping rows that are
        purely layout wrappers (e.g. the all-page outer table that contains the
        navigation AND the content) AND skipping the ``Scope GP W%...`` metrics
        header rows (which in the compact layout are a plain ``tr.child`` and in
        the expanded layout are a nested table inside ``tr.child``).

        Strategy:
        1. Walk every ``<tr>`` in document order.
        2. Skip rows that sit inside a nested sub-table whose rows are pure
           navigation/chrome (detected by checking if the row is inside a table
           whose nearest enclosing ``<tr>`` contains the main parent/team rows
           via a containing ``<td>`` that wraps the sub-table - but more robustly
           we just detect the metrics header row directly via _is_metric_header_row
           and skip any rows that belong to a NESTED metrics table (which has no
           ``tr.parent`` or ``tr.team1row`` of its own, only ``Scope``/``GP``
           labels).
        """
        # First pass: identify tables that are metrics-only sub-tables.  A table
        # is a metrics sub-table if it contains a 'Scope/GP/BTS' header and does
        # NOT contain tr.parent or tr.team1row of its own.  Any row inside such
        # a table is skipped.
        metrics_tables = set()
        for tbl in soup.find_all("table"):
            has_metrics_header = False
            has_data_row = False
            for inner_tr in tbl.find_all("tr", recursive=True):
                classes = set(inner_tr.get("class") or [])
                if "parent" in classes or "team1row" in classes:
                    has_data_row = True
                if self._is_metric_header_row(inner_tr):
                    has_metrics_header = True
            if has_metrics_header and not has_data_row:
                metrics_tables.add(id(tbl))

        for tr in soup.find_all("tr"):
            # Skip tr if it lives inside a metrics-only sub-table.
            parent_tbl = tr.find_parent("table")
            if parent_tbl is not None and id(parent_tbl) in metrics_tables:
                continue
            # Also skip tr.child header rows directly (compact layout uses them
            # without a nested table).
            classes = set(tr.get("class") or [])
            if "child" in classes and self._is_metric_header_row(tr):
                continue
            yield tr

    def _parse_live_index(self, soup: BeautifulSoup, collected_at: datetime) -> List[Match]:
        """Parse current index markup in BOTH layouts:

        * Compact (plain matchday view): ``tr.parent`` league header followed by
          pairs of ``tr.team1row`` / ``tr.team2row``.
        * Expanded (``ms=<filter>`` views): each league is its own sibling
          ``<table>`` with ``tr.parent``, an optional ``tr.child`` containing a
          nested metrics-header table, and then classless ``<tr>`` pairs where the
          home row carries ``<td class="steam"><team>`` plus a ``rowspan="2"``
          kickoff cell and a ``rowspan="2"`` 'stats' anchor, and the away row
          immediately follows it starting at column 1.
        """
        self._collected = collected_at  # for _classify_marker
        matches: List[Match] = []
        competition = "Unknown"
        page_title = self._text(soup.title).lower()
        is_yesterday_results = ("yesterday" in page_title and "result" in page_title) or "results" in page_title

        # Track whether we already saw a team1row (compact) to decide when to skip
        # the expanded-layout parser on the same page (they're mutually exclusive).
        seen_compact_pair = False
        seen_expanded_pair = False

        rows = list(self._iter_index_rows(soup))

        i = 0
        while i < len(rows):
            row = rows[i]
            classes = set(row.get("class") or [])

            if "parent" in classes:
                label = self._text(row.find("td"))
                competition = re.sub(r"\s+stats\s*$", "", label, flags=re.I).strip()
                i += 1
                continue

            if self._is_metric_header_row(row) or "child" in classes:
                # Per-league metrics header / child wrapper; skip.
                i += 1
                continue

            if "team1row" in classes:
                # Compact layout pair
                seen_compact_pair = True
                home_cells = row.find_all("td", recursive=False)
                # find next team2row sibling (skipping nested rows)
                away_row = None
                j = i + 1
                while j < len(rows):
                    cand = rows[j]
                    if "parent" in (cand.get("class") or []):
                        break
                    if "team2row" in (cand.get("class") or []):
                        away_row = cand
                        break
                    if "team1row" in (cand.get("class") or []):
                        break
                    j += 1
                away_cells = away_row.find_all("td", recursive=False) if away_row else []
                if home_cells and away_cells:
                    home = self._text(home_cells[0])
                    away = self._text(away_cells[0])
                    marker = self._text(home_cells[1]) if len(home_cells) > 1 else ""
                    # Compact layout uses rowspan=2 so the away row shares the marker;
                    # if away has a score marker too, use combined.
                    away_marker = self._text(away_cells[1]) if len(away_cells) > 1 else ""
                    if re.fullmatch(r"\d+", marker) and re.fullmatch(r"\d+", away_marker):
                        marker = f"{marker} - {away_marker}"
                    anchor = self._row_team_anchor(row)
                    href = self._absolute(str(anchor["href"])) if anchor else ""
                    status, kickoff = self._classify_marker(marker, href, is_yesterday_results)
                    if home and away:
                        matches.append(self._make_match(competition=competition, home=home, away=away,
                            kickoff=kickoff, time_text=marker, status=status, href=href,
                            collected_at=collected_at))
                i += 1
                continue

            if self._is_expanded_home_row(row):
                seen_expanded_pair = True
                home_cells = row.find_all("td", recursive=False)
                home = self._text(home_cells[0])
                # Find kickoff marker (td with rowspan=2 containing time text)
                marker = ""
                for td in home_cells:
                    if td.get("rowspan") == "2":
                        txt = self._text(td)
                        # The stats button td is rowspan=2 too but contains an <a> with stats label; skip it
                        if txt.lower() in {"stats", "h2h"} or td.find("a", class_="myButton"):
                            continue
                        if re.match(r"\d|\d{1,2}:\d{2}|ft|ht|\d+'|pp", txt, re.I) or txt.strip():
                            marker = txt
                            break
                # away row is the next outer row that starts with a class='steam' td
                # and has NO rowspan=2 (and isn't a parent/header)
                away_row = None
                j = i + 1
                while j < len(rows):
                    cand = rows[j]
                    cclasses = set(cand.get("class") or [])
                    if "parent" in cclasses or self._is_metric_header_row(cand) or "child" in cclasses:
                        break
                    ccells = cand.find_all("td", recursive=False)
                    if ccells and "steam" in (ccells[0].get("class") or []):
                        # Make sure this isn't another home row (shouldn't have rowspan=2)
                        if not any(c.get("rowspan") == "2" for c in ccells):
                            away_row = cand
                            break
                        else:
                            # Another home row - our row had no away; break
                            break
                    j += 1
                away = ""
                away_cells = []
                if away_row is not None:
                    away_cells = away_row.find_all("td", recursive=False)
                    # In expanded layout the away row's first <td> is the team name
                    # (it starts at column 1 in terms of layout, but there is no
                    # leading empty td - the marker cell rowspan=2 occupies column 1
                    # for both rows, and the away row's cells begin at column 2).
                    # The first <td class="steam"> is the away team.
                    away = self._text(away_cells[0])
                    # If score marker wasn't found on home row, check if both rows
                    # have numeric <b> score cells (live/finished)
                    if not marker:
                        # Look for <b>score</b> on both rows
                        hb = row.find("b")
                        ab = away_row.find("b")
                        if hb and ab:
                            marker = f"{self._text(hb)} - {self._text(ab)}"
                anchor = self._row_team_anchor(row)
                href = self._absolute(str(anchor["href"])) if anchor else ""
                status, kickoff = self._classify_marker(marker, href, is_yesterday_results)
                if home and away:
                    matches.append(self._make_match(competition=competition, home=home, away=away,
                        kickoff=kickoff, time_text=marker, status=status, href=href,
                        collected_at=collected_at))
                i = (j + 1) if away_row is not None else (i + 1)
                continue

            i += 1

        return matches

    # Friendly names for the short league slugs seen on by-time pages.
    _BYTIME_LEAGUE_NAMES = {
        "argentina": "Argentina - Liga Profesional",
        "argentina2": "Argentina - Primera Nacional",
        "australia": "Australia - A-League",
        "australia3": "Australia - NPL Victoria",
        "australia7": "Australia - NPL Capital Territory",
        "australia8": "Australia - NPL Northern NSW",
        "australia9": "Australia - NPL Tasmania",
        "australia5": "Australia - NPL South Australia",
        "australia6": "Australia - NPL Western Australia",
        "australia11": "Australia - NPL New South Wales",
        "brazil": "Brazil - Serie A",
        "brazil2": "Brazil - Serie B",
        "brazil3": "Brazil - Serie C",
        "brazil5": "Brazil - Brasileiro Women",
        "bulgaria": "Bulgaria - Parva Liga",
        "bulgaria2": "Bulgaria - Vtora Liga",
        "canada": "Canada - Premier League",
        "chile": "Chile - Liga de Primera",
        "chile2": "Chile - Liga de Ascenso",
        "china": "China - Super League",
        "china2": "China - League One",
        "colombia2": "Colombia - Primera B",
        "copasudamericana": "International - Copa Sudamericana",
        "costarica": "Costa Rica - Primera Div. - Apertura",
        "czechrepublic": "CzechRepublic - 1. Liga",
        "czechrepublic2": "CzechRepublic - FNL",
        "denmark": "Denmark - Superligaen",
        "denmark2": "Denmark - 1st Division",
        "ecuador": "Ecuador - Liga Pro",
        "finland": "Finland - Veikkausliiga",
        "finland2": "Finland - Ykkosliga",
        "finland3": "Finland - Ykkonen",
        "finland4": "Finland - Kakkonen Group A",
        "finland5": "Finland - Kakkonen Group B/C",
        "germany5": "Germany - Regionalliga Nordost",
        "germany8": "Germany - Regionalliga Bayern",
        "guatemala": "Guatemala - Liga Nacional",
        "iceland": "Iceland - Besta deild",
        "iceland2": "Iceland - 1. Deild",
        "iceland3": "Iceland - 2. Deild",
        "ireland": "Ireland - Premier Division",
        "ireland2": "Ireland - First Division",
        "ireland3": "Ireland - Women National League",
        "kazakhstan": "Kazakhstan - Premier League",
        "lithuania": "Lithuania - A Lyga",
        "mexico": "Mexico - Liga MX - Apertura",
        "northmacedonia": "North Macedonia - First League",
        "norway": "Norway - Eliteserien",
        "norway2": "Norway - 1st Division",
        "norway3": "Norway - Division 2",
        "paraguay2": "Paraguay - Primera Div. - Clausura",
        "peru2": "Peru - Liga 1 - Clausura",
        "poland": "Poland - Ekstraklasa",
        "poland2": "Poland - 1. Liga",
        "poland3": "Poland - 2. Liga",
        "romania": "Romania - Liga 1",
        "russia": "Russia - Premier League",
        "southkorea2": "South Korea - K League 2",
        "southkorea4": "South Korea - WK League Women",
        "sweden": "Sweden - Allsvenskan",
        "sweden2": "Sweden - Superettan",
        "sweden3": "Sweden - Allsvenskan Women",
        "usa": "USA - MLS",
        "usa2": "USA - USL Championship",
        "usa3": "USA - USL League One",
        "usa4": "USA - NWSL",
        "uruguay": "Uruguay - Liga AUF Uruguaya - Intermediate",
    }

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

            # Extract links ONLY from direct-child <td> elements.  The by-time
            # page wraps every data row in a nested table, so ``row.find_all("a")``
            # would otherwise leak anchors from *all subsequent* rows.
            detail_href = ""
            league_slug = ""
            for c in cells:
                for a in c.find_all("a", href=True, recursive=False):
                    href = str(a["href"])
                    if not detail_href and any(
                        token in href for token in ("round_details.asp", "pmatch.asp", "h2h.asp", "leagueview_team.asp")
                    ):
                        detail_href = self._absolute(href)
                    if not league_slug and "latest.asp" in href and "league=" in href:
                        try:
                            qs = parse_qs(urlparse(href).query)
                            slug = qs.get("league", [""])[0]
                            if slug:
                                league_slug = slug
                        except Exception:
                            pass

            friendly = self._BYTIME_LEAGUE_NAMES.get(league_slug)
            if friendly:
                competition = friendly
            elif league_slug:
                competition = f"{country_code} - {league_slug}" if country_code else league_slug
            else:
                competition = country_code or "Unknown"

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

    def _extract_metrics_from_cells(self, cells: list[Tag]) -> Optional[Dict[str, float]]:
        """Extract the 12 metric columns (GP, W%, FTS, CS, BTS, TG, GF, GA,
        1.5+, 2.5+, 3.5+, PPG) from a home/away row's direct cells, skipping the
        leading team-name cell and any scope label cell (``Home``/``Away``/``Total``/``last 8``).
        """
        values = [self._text(cell) for cell in cells]
        # Skip leading team-name cell (usually index 0)
        for start in range(len(values)):
            if values[start].lower() in {"home", "away", "total", "last 8"}:
                break
        else:
            return None
        raw = [v for v in values[start + 1:] if v][:12]
        if len(raw) != 12:
            return None
        numbers = [self._number(v) for v in raw]
        if any(v is None for v in numbers):
            return None
        return dict(zip(("gp", "win", "fts", "cs", "btts", "tg", "gf", "ga", "over15", "over25", "over35", "ppg"), numbers))

    def parse_index_features(self, content: bytes, collected_at: datetime, feature_scope: str = "home_away") -> List[Features]:
        soup = BeautifulSoup(content, "lxml")
        if soup.find("table", id="btable"):
            return []
        # by-time flat view has no per-team stats columns
        if "matches by time" in self._text(soup.title).lower():
            return []
        matches = self._parse_live_index(soup, collected_at)
        by_pair = {(m.home_team, m.away_team): m for m in matches if m.status == "pre-match"}
        features: List[Features] = []

        def emit(home_team: str, away_team: str, home_cells: list[Tag], away_cells: list[Tag]) -> None:
            match = by_pair.get((home_team, away_team))
            if not match:
                return
            home_m = self._extract_metrics_from_cells(home_cells)
            away_m = self._extract_metrics_from_cells(away_cells)
            if not home_m or not away_m:
                return
            features.append(Features(
                match_id=match.match_id, collected_at=collected_at, feature_cutoff=collected_at,
                match_kickoff=match.scheduled_kickoff, data_type="pre-match", source_status="pre-match", feature_scope=feature_scope,
                home_ppg=home_m["ppg"], away_ppg=away_m["ppg"],
                home_win_rate=home_m["win"] / 100.0, away_win_rate=away_m["win"] / 100.0,
                home_failed_to_score_rate=home_m["fts"] / 100.0, away_failed_to_score_rate=away_m["fts"] / 100.0,
                home_clean_sheet_rate=home_m["cs"] / 100.0, away_clean_sheet_rate=away_m["cs"] / 100.0,
                btts_rate_home=home_m["btts"] / 100.0, btts_rate_away=away_m["btts"] / 100.0,
                home_total_goals_avg=home_m["tg"], away_total_goals_avg=away_m["tg"],
                home_goals_scored_avg=home_m["gf"], away_goals_scored_avg=away_m["gf"],
                home_goals_conceded_avg=home_m["ga"], away_goals_conceded_avg=away_m["ga"],
                over_15_rate_home=home_m["over15"] / 100.0, over_15_rate_away=away_m["over15"] / 100.0,
                over_25_rate_home=home_m["over25"] / 100.0, over_25_rate_away=away_m["over25"] / 100.0,
                over_35_rate_home=home_m["over35"] / 100.0, over_35_rate_away=away_m["over35"] / 100.0,
                sample_size_home=int(home_m["gp"]), sample_size_away=int(away_m["gp"]),
            ))

        rows = list(self._iter_index_rows(soup))
        i = 0
        while i < len(rows):
            row = rows[i]
            classes = set(row.get("class") or [])
            if "parent" in classes or self._is_metric_header_row(row) or "child" in classes:
                i += 1
                continue
            if "team1row" in classes:
                home_cells = row.find_all("td", recursive=False)
                # Find paired team2row
                away_row = None
                j = i + 1
                while j < len(rows):
                    cand = rows[j]
                    cclasses = set(cand.get("class") or [])
                    if "parent" in cclasses or "team1row" in cclasses:
                        break
                    if "team2row" in cclasses:
                        away_row = cand
                        break
                    j += 1
                if away_row is not None:
                    away_cells = away_row.find_all("td", recursive=False)
                    home = self._text(home_cells[0]) if home_cells else ""
                    away = self._text(away_cells[0]) if away_cells else ""
                    if home and away:
                        emit(home, away, home_cells, away_cells)
                    i = j + 1
                    continue
            if self._is_expanded_home_row(row):
                home_cells = row.find_all("td", recursive=False)
                home = self._text(home_cells[0]) if home_cells else ""
                # Find away row (next outer row with class steam, no rowspan=2)
                away_row = None
                j = i + 1
                while j < len(rows):
                    cand = rows[j]
                    cclasses = set(cand.get("class") or [])
                    if "parent" in cclasses or self._is_metric_header_row(cand) or "child" in cclasses:
                        break
                    ccells = cand.find_all("td", recursive=False)
                    if ccells and "steam" in (ccells[0].get("class") or []):
                        if not any(c.get("rowspan") == "2" for c in ccells):
                            away_row = cand
                            break
                        else:
                            break
                    j += 1
                if away_row is not None:
                    # away row starts at column 1 in layout (no leading marker cell),
                    # so prepend a dummy cell so column indices match the home row.
                    away_cells_raw = away_row.find_all("td", recursive=False)
                    dummy = soup.new_tag("td")
                    padded = [dummy] + list(away_cells_raw)
                    away = self._text(away_cells_raw[0]) if away_cells_raw else ""
                    if home and away:
                        emit(home, away, home_cells, padded)
                    i = j + 1
                    continue
            i += 1
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

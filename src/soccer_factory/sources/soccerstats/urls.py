"""URL construction for public SoccerStats endpoints.

PATCHED (2026-07-24):
The default SoccerStats matchday pages (matchday=0/1/2/100/101/102/200/201/202) render only FEATURED leagues
when no ``ms=`` query parameter is supplied.  Any ``ms=<filter>`` switches the server to the expanded
vertical-pair layout (the same markup the browser gets after "Show all matches"), but each ``ms`` value
is a statistical preset and only returns leagues whose matches pass that preset's filter.  Fan-out
across a curated set of filters is required to expose every league SoccerStats lists publicly.

Fan-out strategy used here (covers all 60+ league parent rows for tomorrow, without hitting per-league
``latest.asp?league=...``):
  * base matchday tokens:
      yesterday -> 0, 100, 200   (full in plain view)
      today     -> 1, 101, 201, 6, 106, 206   (grouped + by-time flat views)
      tomorrow  -> 2, 102, 202
  * expanded filters (``ms=``):
      ("a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p","q","r")
    Any single filter misses many leagues; the union of these 18 filters exposes every parent league
    the public site renders, including Iceland / Ireland / Poland / Sweden / Bulgaria / etc.

Daily indexes:
* matchday=0,100,200 with daym=yesterday – yesterday's results (compact home/away, full)
* matchday=1,101,201 – today grouped (featured only in plain view)
* matchday=6,106,206 – today by-time flat view (server-side flat, not featured-filtered)
* matchday=2,102,202 with daym=tomorrow – tomorrow grouped (featured only in plain view)
"""

from __future__ import annotations

from typing import List, Tuple
from urllib.parse import parse_qs, urlparse

# Base URLs
_MATCHES_BASE = "https://www.soccerstats.com/matches.asp"
_LATEST_BASE = "https://www.soccerstats.com/latest.asp"

# Curated set of ms= statistical filters whose union returns every league SoccerStats
# lists publicly for a given day.  Empirically verified live on 2026-07-24 against
# matchday=202 (tomorrow); covers Argentina / Australia / Brazil / Bulgaria / Canada /
# Chile / China / Colombia / Costa Rica / CzechRepublic / Denmark / Ecuador / Finland /
# Germany / Guatemala / Iceland / Ireland / Kazakhstan / Lithuania / Mexico /
# North Macedonia / Norway / Paraguay / Peru / Poland / Romania / Russia / South Korea /
# Sweden / Uruguay / USA / etc.
_EXPANDED_FILTERS: Tuple[str, ...] = (
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r",
)

# Plain view returns ALL yesterday matches (it's a results page, not a featured selection),
# so no ms= fan-out is needed for yesterday.
_YESTERDAY_BASES: Tuple[str, ...] = (
    "matchday=0&daym=yesterday&matchdayn=1",
    "matchday=100&daym=yesterday&matchdayn=1",
    "matchday=200&daym=yesterday&matchdayn=1",
)

# Today: grouped (featured when plain) + by-time flat (which is not featured-filtered).
# We still fan the grouped tokens across ms= filters so parser sees the expanded
# vertical layout with all league parent rows, and include by-time as a redundant
# flat source.
_TODAY_GROUPED_BASES: Tuple[str, ...] = (
    "matchday=1&matchdayn=1",
    "matchday=101&matchdayn=1",
    "matchday=201&matchdayn=1",
)
_TODAY_BYTIME_BASES: Tuple[str, ...] = (
    "matchday=6&matchdayn=1",
    "matchday=106&matchdayn=1",
    "matchday=206&matchdayn=1",
)

# Tomorrow: only grouped endpoints exist (6/106/206 returns a server error for tomorrow);
# fan-out across ms= filters is required to see all leagues.
_TOMORROW_BASES: Tuple[str, ...] = (
    "matchday=2&daym=tomorrow&matchdayn=1",
    "matchday=102&daym=tomorrow&matchdayn=1",
    "matchday=202&daym=tomorrow&matchdayn=1",
)


def _with_filters(bases: Tuple[str, ...], add_filters: bool) -> List[str]:
    """Expand a set of base query strings with optional ``&ms=<filter>`` fan-out."""
    urls: List[str] = []
    for base in bases:
        urls.append(f"{_MATCHES_BASE}?{base}")
        if add_filters:
            for ms in _EXPANDED_FILTERS:
                urls.append(f"{_MATCHES_BASE}?{base}&ms={ms}")
    return urls


def get_matches_url(date_str: str) -> str:
    """Backwards-compatible single-URL helper used by legacy callers."""
    return f"{_MATCHES_BASE}?matchday={date_str}"


def get_match_url(match_id: str) -> str:
    return f"https://www.soccerstats.com/pmatch.asp?league=england&matchid={match_id}"


def daily_index_urls(offset_days: int) -> List[str]:
    """Return the full set of daily index URLs for a relative day offset.

    offset_days == -1 -> yesterday (3 URLs, plain results, full)
    offset_days == 0  -> today (3 grouped plain + 3 grouped*18 ms= filters + 3 by-time = 60 URLs)
    offset_days == 1  -> tomorrow (3 plain + 3*18 ms= filters = 57 URLs)
    """
    if offset_days == -1:
        return _with_filters(_YESTERDAY_BASES, add_filters=False)
    if offset_days == 0:
        # Grouped bases with expanded fan-out + by-time flat views (already full, no fan-out needed)
        grouped = _with_filters(_TODAY_GROUPED_BASES, add_filters=True)
        bytime = _with_filters(_TODAY_BYTIME_BASES, add_filters=False)
        return grouped + bytime
    if offset_days == 1:
        return _with_filters(_TOMORROW_BASES, add_filters=True)
    raise ValueError(
        "SoccerStats public daily index only supports yesterday (-1), today (0), tomorrow (+1)"
    )


def index_scope(url: str) -> str:
    """Human-readable scope label for a given index URL (records which filter/scope produced it)."""
    qs = parse_qs(urlparse(url).query)
    matchday = qs.get("matchday", [""])[0]
    ms = qs.get("ms", [""])[0]
    mapping = {
        "0": "results",
        "1": "home_away",
        "2": "home_away",
        "6": "by_time_home_away",
        "100": "results_all_games",
        "101": "all_games",
        "102": "all_games",
        "106": "by_time_all_games",
        "200": "results_last_8",
        "201": "last_8",
        "202": "last_8",
        "206": "by_time_last_8",
    }
    base = mapping.get(matchday, f"unknown_{matchday}")
    if ms:
        return f"{base}_expanded_{ms}"
    return base


def league_latest_url(league_slug: str) -> str:
    """Return the full-match listing URL for a single league."""
    return f"{_LATEST_BASE}?league={league_slug}"


def all_league_latest_urls() -> List[Tuple[str, str]]:
    """Return (slug, url) pairs for every public league the site exposes.

    Tries to import from leagues.py, falls back to dynamic extraction if file missing.
    """
    try:
        from .leagues import LEAGUE_SLUGS
        slugs = LEAGUE_SLUGS
    except ImportError:
        slugs = [
            "brazil", "brazil2", "ecuador", "usa", "usa2", "england", "spain",
            "germany", "italy", "france", "argentina", "argentina2"
        ]
    return [(slug, league_latest_url(slug)) for slug in slugs]

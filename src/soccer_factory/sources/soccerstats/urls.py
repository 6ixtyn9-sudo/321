"""URL construction for public SoccerStats endpoints.

Daily indexes:
* matchday=0,100,200 with daym=yesterday – yesterday's results (home/away, all_games, last_8) FULL 30
* matchday=1,101,201 – today grouped (home/away, all_games, last_8) LIMITED to 10 public
* matchday=6,106,206 – today by-time (home/away, all_games, last_8) FULL 31 - bypasses limit
* matchday=2,102,202 with daym=tomorrow – tomorrow grouped LIMITED 10, needs league fallback
* matchday=0,100,200 without daym also return yesterday (same as with daym)

The by-time views (6,106,206) are the only public pages that return full 31 for today without member.
For tomorrow, full list requires league enumeration via latest.asp?league=...
"""

from __future__ import annotations

from typing import List, Tuple

# Base URLs
_MATCHES_BASE = "https://www.soccerstats.com/matches.asp"
_LATEST_BASE = "https://www.soccerstats.com/latest.asp"


def get_matches_url(date_str: str) -> str:
    """Backwards-compatible single-URL helper used by legacy callers."""
    return f"{_MATCHES_BASE}?matchday={date_str}"


def get_match_url(match_id: str) -> str:
    return f"https://www.soccerstats.com/pmatch.asp?league=england&matchid={match_id}"


def daily_index_urls(offset_days: int) -> List[str]:
    """Return the full set of daily index URLs for a relative day offset.

    offset_days == -1 → yesterday (FULL), 0 → today (6 urls: 3 limited grouped + 3 full by-time), +1 → tomorrow (limited, needs fallback)
    
    This version mirrors live.py's daily_index_urls(target, today) but uses offset only.
    For today, it correctly returns by-time 6,106,206 (FULL) NOT 0,100,200 which are yesterday.
    """
    if offset_days == -1:
        return [
            f"{_MATCHES_BASE}?matchday=0&daym=yesterday&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=100&daym=yesterday&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=200&daym=yesterday&matchdayn=1",
        ]
    if offset_days == 0:
        return [
            f"{_MATCHES_BASE}?matchday=1&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=101&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=201&matchdayn=1",
            # By-time views - FULL 31, bypass 10 limit
            f"{_MATCHES_BASE}?matchday=6&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=106&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=206&matchdayn=1",
        ]
    if offset_days == 1:
        return [
            f"{_MATCHES_BASE}?matchday=2&daym=tomorrow&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=102&daym=tomorrow&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=202&daym=tomorrow&matchdayn=1",
        ]
    raise ValueError(
        "SoccerStats public daily index only supports yesterday (-1), today (0), tomorrow (+1)"
    )


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
        # Fallback minimal list - will be expanded by live fetch of leagues.asp
        slugs = [
            "brazil", "brazil2", "ecuador", "usa", "usa2", "england", "spain",
            "germany", "italy", "france", "argentina", "argentina2"
        ]
    return [(slug, league_latest_url(slug)) for slug in slugs]

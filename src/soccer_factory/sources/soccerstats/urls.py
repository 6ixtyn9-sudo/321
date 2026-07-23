"""URL construction for public SoccerStats endpoints.

Daily indexes:
* ``matchday=0``  – yesterday's results (home/away scope, 30-match un-capped view)
* ``matchday=100`` – today's matches "All games" scope (un-capped 30-match view)
* ``matchday=200`` – today's matches "by time" / "last 8" scope (un-capped 30-match view)
* ``matchday=2``  – tomorrow's matches (home/away scope, 10-match public cap)
* ``matchday=102`` – tomorrow's "All games" scope
* ``matchday=202`` – tomorrow's "last 8" scope

The un-capped 30-match URLs (0/100/200) are the "Matches from favourite
leagues / by time" index variants and return the largest set the public
site will serve without authentication.
"""
from __future__ import annotations

from .leagues import LEAGUE_SLUGS

_MATCHES_BASE = "https://www.soccerstats.com/matches.asp"
_LATEST_BASE = "https://www.soccerstats.com/latest.asp"


def get_matches_url(date_str: str) -> str:
    """Backwards-compatible single-URL helper used by legacy callers."""
    return f"{_MATCHES_BASE}?matchday={date_str}"


def get_match_url(match_id: str) -> str:
    return f"https://www.soccerstats.com/pmatch.asp?league=england&matchid={match_id}"


def daily_index_urls(offset_days: int) -> list[str]:
    """Return the full set of daily index URLs for a relative day offset.

    offset_days == -1 → yesterday, 0 → today, +1 → tomorrow.
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
            # The "by time" / un-capped favourites listing is also fetched
            # because it exposes up to 30 rows instead of the 10-match cap.
            f"{_MATCHES_BASE}?matchday=0&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=100&matchdayn=1",
            f"{_MATCHES_BASE}?matchday=200&matchdayn=1",
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


def all_league_latest_urls() -> list[tuple[str, str]]:
    """Return (slug, url) pairs for every public league the site exposes."""
    return [(slug, league_latest_url(slug)) for slug in LEAGUE_SLUGS]

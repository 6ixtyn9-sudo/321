"""Forebet URL routing.

The HTML pages at ``/en/football-tips-and-predictions-for-{today,tomorrow,...}``
render client-side from a JSON XHR endpoint::

    https://www.forebet.com/scripts/getrs.php?ln=en&tp={market}&in=YYYY-MM-DD&ord=0&tz=0&tzs=&tze=

Every market shares the same match ``id``, so we fan out across ``tp`` codes and
merge by id to obtain one wide record per match.  The HTML pages themselves are
not useful as a data source (``div.rcnt`` rows render only with JS).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

_JSON_BASE = "https://www.forebet.com/scripts/getrs.php"
_PREDICTIONS_BASE = "https://www.forebet.com/en/football-tips-and-predictions-for-"

# All known ``tp`` codes the JSON endpoint accepts, keyed by a local market name.
# Each entry is (tp_code, human_label, is_core).  Core markets are fetched by
# default; extended markets are fetched only when explicitly requested.
MARKETS: Dict[str, Tuple[str, str, bool]] = {
    "1x2":      ("1x2",  "1X2 result",                    True),
    "uo":       ("uo",   "Over/Under 2.5 goals",          True),
    "bts":      ("bts",  "Both teams to score",           True),
    "ht":       ("ht",   "Half-time result",              False),
    "htft":     ("htft", "Half-time / Full-time",         False),
    "ah":       ("ah",   "Asian handicap",                False),
    "corners":  ("corners", "Corners",                    False),
    "cards":    ("cards", "Cards/bookings",               False),
}

# tp codes that don't return data on the live site (discovered empirically):
#   dc, cs, gs, ttg, 2up, 3up, dnb, goalscorers (HTML widget only)
# Double-chance is computed client-side from 1X2 probabilities (1X, X2, 12).


def _market_url(date_str: str, tp: str, referer_day: str = "today") -> str:
    return (
        f"{_JSON_BASE}?ln=en&tp={tp}&in={date_str}"
        f"&ord=0&tz=0&tzs=&tze="
    )


def daily_market_urls(date_str: str, markets: List[str]) -> List[Tuple[str, str]]:
    """Return ``(market_name, url)`` pairs for the given calendar day.

    The Referer used by the collector is the HTML ``football-tips-and-predictions-for-<day>``
    page; the XHR endpoint requires that header to serve data.
    """
    return [(m, _market_url(date_str, MARKETS[m][0])) for m in markets if m in MARKETS]


def predictions_html_url(day: str = "today") -> str:
    """HTML shell URL, useful as a Referer and for debugging in a browser."""
    return f"{_PREDICTIONS_BASE}{day}"


def json_headers(referer_day: str = "today") -> Dict[str, str]:
    """Headers the JSON endpoint requires (403s without UA+Referer+XHR)."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": predictions_html_url(referer_day),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }


def core_markets() -> List[str]:
    return [m for m, spec in MARKETS.items() if spec[2]]


def all_markets() -> List[str]:
    return list(MARKETS.keys())

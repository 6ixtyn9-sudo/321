"""
URL classifier for discovered pages.

classify(url, source) -> page_family string.
classify_outcome(url, source) -> (category, family) tuple.

Categories:
    known       — URL matched one of the defined page families
    unknown     — URL is on the allowed domain but doesn't match any family
    restricted  — URL is blocked by policy (path, extension, scheme)
    external    — URL is outside the allowed domain

All logic is pure (no I/O).  Uses urllib.parse + string matching.
"""
from __future__ import annotations

import urllib.parse
from typing import Tuple

from .policy import is_same_domain, is_valid_scheme


# ---------------------------------------------------------------------------
# SoccerStats families
# ---------------------------------------------------------------------------

SS_FAMILIES: list[str] = [
    "homepage",
    "matches",
    "match_preview",
    "results",
    "round_details",
    "league_latest",
    "league_view",
    "home_away",
    "form_table",
    "wide_table",
    "stats_by_month",
    "trends",
    "favourite_stats",
    "generic_table",
    "match_list",
    "team_stats",
    "leagueview_team",
    "statistical_overview",
    "faq",
    "legal",
    "member_or_restricted",
    "unknown",
]

FB_FAMILIES: list[str] = [
    "daily_predictions",
    "tomorrow_predictions",
    "weekend_predictions",
    "finished_predictions",
    "live_predictions",
    "result_market",
    "goals_market",
    "half_time",
    "half_time_full_time",
    "btts",
    "double_chance",
    "asian_handicap",
    "goalscorers",
    "corners",
    "cards",
    "by_country",
    "by_league",
    "prediction_list",
    "top_predictions",
    "values_or_odds",
    "unknown",
]


def _parse(url: str) -> tuple[str, str, str]:
    """Return (path_lower, query_lower, fragment_lower)."""
    p = urllib.parse.urlparse(url)
    return p.path.lower(), p.query.lower(), p.fragment.lower()


def _qs(query: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(query)


# ---------------------------------------------------------------------------
# SoccerStats classifier
# ---------------------------------------------------------------------------

def classify_soccerstats(url: str) -> str:
    """Return the SoccerStats page family for *url*.

    Always returns one of SS_FAMILIES (never raises).
    """
    path, query, _ = _parse(url)

    # Restricted / member pages — classified before generic checks
    if any(k in path for k in ("members", "register", "login", "payment", "subscription")):
        return "member_or_restricted"

    # FAQ
    if "faq" in path:
        return "faq"

    # Legal
    if any(k in path for k in ("privacy", "cookie", "terms", "legal", "about", "contact")):
        return "legal"

    # Match preview  pmatch.asp
    if "pmatch.asp" in path:
        return "match_preview"

    # Round details
    if "round_details.asp" in path:
        return "round_details"

    # Results
    if "results.asp" in path:
        return "results"

    # Match list
    if "matchlist.asp" in path:
        return "match_list"

    # Matches (all parameter variants)
    if "matches.asp" in path:
        return "matches"

    # Latest league page
    if "latest.asp" in path:
        return "league_latest"

    # Team-vs-team league view (must precede leagueview.asp)
    if "leagueview_team.asp" in path:
        return "leagueview_team"

    if "leagueview.asp" in path:
        return "league_view"

    # Home/Away
    if "homeaway.asp" in path:
        return "home_away"

    # Form table
    if "formtable.asp" in path:
        return "form_table"

    # Wide table
    if "widetable.asp" in path:
        return "wide_table"

    # Stats by month
    if "statsbymonth.asp" in path:
        return "stats_by_month"

    # Trends
    if "trends.asp" in path:
        return "trends"

    # Favourite stats
    if "fstats.asp" in path:
        return "favourite_stats"

    # Generic table
    if "table.asp" in path:
        return "generic_table"

    # Team stats
    if "teamstats.asp" in path:
        return "team_stats"

    # Statistical overview  stats.asp
    if "stats.asp" in path:
        return "statistical_overview"

    # Leagues / homepage-level entry points
    if "leagues.asp" in path:
        return "matches"   # treat as entry-point alongside matches

    # Homepage
    if path in ("/", "", "/index.asp", "/index.html", "/default.asp"):
        return "homepage"

    return "unknown"


# ---------------------------------------------------------------------------
# Forebet classifier
# ---------------------------------------------------------------------------

def classify_forebet(url: str) -> str:
    """Return the Forebet page family for *url*.

    Always returns one of FB_FAMILIES (never raises).
    """
    path, query, _ = _parse(url)

    # Values / odds — excluded
    if any(k in path for k in ("value", "values", "odds", "odds-comparison", "bookmaker")):
        return "values_or_odds"

    # Daily predictions
    if "football-tips-and-predictions-for-today" in path:
        return "daily_predictions"

    # Tomorrow
    if "football-tips-and-predictions-for-tomorrow" in path:
        return "tomorrow_predictions"

    # Weekend
    if "weekend" in path:
        return "weekend_predictions"

    # Finished / yesterday
    if any(k in path for k in ("yesterday", "finished", "predictions-from")):
        return "finished_predictions"

    # Live
    if "live" in path:
        return "live_predictions"

    # Specific markets — ordered most-specific first
    if any(k in path for k in ("half-time-full-time", "ht-ft", "htft")):
        return "half_time_full_time"

    if any(k in path for k in ("over-under", "over_under", "goal-")):
        return "goals_market"

    if "half-time" in path or "/ht/" in path:
        return "half_time"

    if any(k in path for k in ("both-teams", "btts", "both_teams")):
        return "btts"

    if any(k in path for k in ("double-chance", "double_chance")):
        return "double_chance"

    if any(k in path for k in ("asian-handicap", "asian_handicap", "handicap")):
        return "asian_handicap"

    if any(k in path for k in ("goalscorer", "scorer")):
        return "goalscorers"

    if "corner" in path:
        return "corners"

    if any(k in path for k in ("/card", "yellow-card", "red-card")):
        return "cards"

    if "1x2" in path or "/result-" in path:
        return "result_market"

    # Top predictions
    if "top" in path and "predict" in path:
        return "top_predictions"

    # By country — /en/football-predictions/{country}/...
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and "football-predictions" in parts:
        idx = parts.index("football-predictions") if "football-predictions" in parts else -1
        if idx >= 0 and idx + 1 < len(parts):
            return "by_country"

    # By league / general prediction list
    if "football-predictions" in path or "football-tips" in path:
        return "prediction_list"

    return "unknown"


# ---------------------------------------------------------------------------
# Unified classifier
# ---------------------------------------------------------------------------

def classify(url: str, source: str) -> str:
    """Dispatch to source-specific classifier.  Returns family string."""
    if source == "soccerstats":
        return classify_soccerstats(url)
    if source == "forebet":
        return classify_forebet(url)
    return "unknown"


def classify_outcome(url: str, source: str) -> Tuple[str, str]:
    """Return (category, family).

    category is one of:  known | unknown | restricted | external

    - restricted: URL is blocked by policy (scheme, path, extension)
    - external:   URL is not on the allowed domain
    - unknown:    On-domain URL that doesn't match any defined family
    - known:      Matched a defined page family
    """
    # Scheme / restricted check first
    if not is_valid_scheme(url):
        return ("restricted", "restricted")

    from . import policy as _policy  # avoid circular at module level
    if _policy.is_restricted(url):
        return ("restricted", "restricted")

    # Domain check
    if not is_same_domain(url, source):
        return ("external", "external")

    # Family classification
    family = classify(url, source)
    if family == "unknown":
        return ("unknown", "unknown")

    return ("known", family)


def all_families(source: str) -> list[str]:
    """Return the complete list of defined families for *source*."""
    if source == "soccerstats":
        return list(SS_FAMILIES)
    if source == "forebet":
        return list(FB_FAMILIES)
    return []

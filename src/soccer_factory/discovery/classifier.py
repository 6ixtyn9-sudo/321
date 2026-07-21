"""
URL classifier for discovered pages.

classify(url, source) -> page_family string.
classify_outcome(url, source) -> (category, family) tuple.

Categories:
    known       — URL matched one of the defined page families
    unknown     — URL is on the allowed domain but doesn't match any family
    restricted  — URL is blocked by policy (path, extension, scheme)
    external    — URL is outside the allowed domain
    values_or_odds - values or odds pages (for forebet)
    non_soccer - non-soccer sports (for forebet)
"""
from __future__ import annotations

import urllib.parse
from typing import Tuple

from .policy import is_same_domain, is_valid_scheme


# ---------------------------------------------------------------------------
# SoccerStats families
# ---------------------------------------------------------------------------

SS_FAMILIES: list[str] = [
    "matches",
    "match_preview",
    "league_latest",
    "league_view",
    "leagueview_team",
    "results",
    "round_details",
    "home_away",
    "form_table",
    "wide_table",
    "stats_by_month",
    "statistical_overview",
    "statistics_by_date",
    "generic_table",
    "match_list",
    "team_stats",
    "run_in",
    "relative_form",
    "projected_points",
    "performance_rating",
    "home_advantage",
    "current_streaks",
    "over_under",
    "total_goals",
    "goal_ranges",
    "average_goals",
    "scored_conceded",
    "both_teams_scored",
    "goal_margins",
    "goal_timing",
    "goals_by_10_minutes",
    "goals_by_15_minutes",
    "first_goal",
    "scored_both_halves",
    "lead_durations",
    "leading_trailing",
    "goal_types",
    "equalisers",
    "faq",
    "legal",
    "restricted",
    "external",
    "unknown",
    "homepage"
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
    "football_match",
    "match_detail",
    "match_preview_index",
    "match_preview_article",
    "trends",
    "top_trends",
    "livescore",
    "injured_players",
    "team_comparison",
    "team_page",
    "prediction_list",
    "country_page",
    "competition_page",
    "site_information",
    "values_or_odds",
    "non_soccer",
    "restricted",
    "external",
    "unknown"
]


def _parse(url: str) -> tuple[str, str, str]:
    """Return (path_lower, query_lower, fragment_lower)."""
    p = urllib.parse.urlparse(url)
    return p.path.lower(), p.query.lower(), p.fragment.lower()


# ---------------------------------------------------------------------------
# SoccerStats classifier
# ---------------------------------------------------------------------------

def classify_soccerstats(url: str) -> str:
    """Return the SoccerStats page family for *url*.

    Always returns one of SS_FAMILIES (never raises).
    """
    path, query, _ = _parse(url)
    url_lower = url.lower()

    # Restricted / member pages — classified before generic checks
    if any(k in path for k in ("members", "register", "login", "payment", "subscription")):
        return "restricted"

    if "faq" in path:
        return "faq"

    if any(k in path for k in ("privacy", "cookie", "terms", "legal", "about", "contact")):
        return "legal"

    # Specific statistical sections / queries
    if "run_in" in url_lower or "runin" in url_lower: return "run_in"
    if "relative_form" in url_lower or "relativeform" in url_lower: return "relative_form"
    if "projected" in url_lower: return "projected_points"
    if "performance" in url_lower: return "performance_rating"
    if "home_advantage" in url_lower or "homeadvantage" in url_lower: return "home_advantage"
    if "streaks" in url_lower: return "current_streaks"
    if "over_under" in url_lower or "overunder" in url_lower: return "over_under"
    if "total_goals" in url_lower or "totalgoals" in url_lower: return "total_goals"
    if "goal_ranges" in url_lower or "goalranges" in url_lower: return "goal_ranges"
    if "average_goals" in url_lower or "averagegoals" in url_lower: return "average_goals"
    if "scored_conceded" in url_lower or "scoredconceded" in url_lower: return "scored_conceded"
    if "both_teams_scored" in url_lower or "btts" in url_lower: return "both_teams_scored"
    if "goal_margins" in url_lower or "goalmargins" in url_lower: return "goal_margins"
    if "10_minutes" in url_lower or "10min" in url_lower: return "goals_by_10_minutes"
    if "15_minutes" in url_lower or "15min" in url_lower: return "goals_by_15_minutes"
    if "timing" in url_lower: return "goal_timing"
    if "first_goal" in url_lower or "firstgoal" in url_lower: return "first_goal"
    if "both_halves" in url_lower or "bothhalves" in url_lower: return "scored_both_halves"
    if "lead_durations" in url_lower or "leaddurations" in url_lower: return "lead_durations"
    if "leading_trailing" in url_lower or "leadingtrailing" in url_lower: return "leading_trailing"
    if "goal_types" in url_lower or "goaltypes" in url_lower: return "goal_types"
    if "equaliser" in url_lower: return "equalisers"
    if "statistics_by_date" in url_lower or "bydate" in url_lower: return "statistics_by_date"

    # ASP Paths
    if "pmatch.asp" in path:
        return "match_preview"

    if "round_details.asp" in path:
        return "round_details"

    if "results.asp" in path:
        return "results"

    if "matchlist.asp" in path:
        return "match_list"

    if "matches.asp" in path:
        return "matches"

    if "latest.asp" in path:
        return "league_latest"

    if "leagueview_team.asp" in path:
        return "leagueview_team"

    if "leagueview.asp" in path:
        return "league_view"

    if "homeaway.asp" in path:
        return "home_away"

    if "formtable.asp" in path:
        return "form_table"

    if "widetable.asp" in path:
        return "wide_table"

    if "statsbymonth.asp" in path:
        return "stats_by_month"

    if "trends.asp" in path:
        return "trends"

    if "table.asp" in path:
        return "generic_table"

    if "teamstats.asp" in path:
        return "team_stats"

    if "stats.asp" in path:
        return "statistical_overview"

    if "leagues.asp" in path:
        return "matches"

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

    # Non-soccer sports
    if any(k in path for k in ("/tennis", "/basketball", "/hockey", "/rugby", "/cricket", "/volleyball", "/handball", "/esports")):
        return "non_soccer"

    if any(k in path for k in ("privacy", "terms", "cookie", "contact", "about", "faq")):
        return "site_information"

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
    if "live-football-tips" in path or "livescore" in path:
        if "livescore" in path:
            return "livescore"
        return "live_predictions"

    # Match detail and Previews
    if "football-match-previews" in path:
        # Check if it has a numeric id indicating an article
        parts = [p for p in path.split("/") if p]
        if parts[-1] != "football-match-previews" and any(c.isdigit() for c in parts[-1].split("-")[0]):
            return "match_preview_article"
        return "match_preview_index"

    if "/football/matches/" in path:
        return "football_match"

    if "/teams/" in path:
        return "team_page"

    if "injured-players" in path:
        return "injured_players"

    if "team-comparison" in path:
        return "team_comparison"

    if "/trends/top" in path or "/top-trends" in path:
        return "top_trends"

    if "/trends" in path:
        return "trends"

    # Specific markets
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
            if idx + 2 < len(parts):
                return "competition_page"
            return "country_page"

    # By league / general prediction list
    if any(k in path for k in ("football-predictions", "football-tips", "prediction-list")):
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

    category is one of:  known | unknown | restricted | external | values_or_odds | non_soccer

    - restricted: URL is blocked by policy (scheme, path, extension)
    - external:   URL is not on the allowed domain
    - values_or_odds: explicitly mapped to values/odds pages
    - non_soccer: explicitly mapped to non-soccer pages
    - unknown:    On-domain URL that doesn't match any defined family
    - known:      Matched a defined page family
    """
    if not is_valid_scheme(url):
        return ("restricted", "restricted")

    from . import policy as _policy  # avoid circular at module level
    if _policy.is_restricted(url):
        return ("restricted", "restricted")

    if not is_same_domain(url, source):
        return ("external", "external")

    family = classify(url, source)
    
    if family == "unknown":
        return ("unknown", "unknown")
        
    if family == "restricted":
        return ("restricted", "restricted")
        
    if family == "values_or_odds":
        return ("values_or_odds", "values_or_odds")
        
    if family == "non_soccer":
        return ("non_soccer", "non_soccer")

    return ("known", family)


def all_families(source: str) -> list[str]:
    """Return the complete list of defined families for *source*."""
    if source == "soccerstats":
        return list(SS_FAMILIES)
    if source == "forebet":
        return list(FB_FAMILIES)
    return []

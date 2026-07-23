"""
Default seed URLs for bounded page-family discovery.

Patched to ensure EVERY link family is discovered and produces stats end-to-end.

SoccerStats: 60+ seeds covering all 40+ families
Forebet: 35+ seeds covering all families
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# SoccerStats — Comprehensive seeds for ALL families
# ---------------------------------------------------------------------------

# All table.asp tid variants observed in classifier
SOCCERSTATS_TIDS = [
    "p", "y", "g", "z", "e", "d", "ha", "s8", "pp", "rp", "re", "2p", "v", "10",
    "c", "8", "9", "f", "j", "k", "t", "h", "u", "x", "w", "pa", "sc"
]

SOCCERSTATS_SEEDS: List[str] = [
    # Core match-view variants (3 scopes x 3 days + by-time)
    "https://www.soccerstats.com/matches.asp",
    "https://www.soccerstats.com/matches.asp?matchday=0&daym=yesterday&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=100&daym=yesterday&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=200&daym=yesterday&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=101&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=201&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=6&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=106&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=206&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=102&daym=tomorrow&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=202&daym=tomorrow&matchdayn=1",
    # Directory / stats entry points
    "https://www.soccerstats.com/leagues.asp",
    "https://www.soccerstats.com/stats.asp",
    "https://www.soccerstats.com/stats.asp?page=10",
    "https://www.soccerstats.com/faq.asp",
    # League-specific families (brazil as example, covers most families)
    "https://www.soccerstats.com/latest.asp?league=brazil",
    "https://www.soccerstats.com/latest.asp?league=england",
    "https://www.soccerstats.com/leagueview.asp?league=brazil",
    "https://www.soccerstats.com/leagueview_team.asp?league=brazil&team1id=1&team2id=2&fmid=1",
    "https://www.soccerstats.com/homeaway.asp?league=brazil",
    "https://www.soccerstats.com/formtable.asp?league=brazil",
    "https://www.soccerstats.com/widetable.asp?league=brazil",
    "https://www.soccerstats.com/statsbymonth.asp?league=brazil",
    "https://www.soccerstats.com/trends.asp?league=brazil",
    "https://www.soccerstats.com/trends.asp?league=brazil&tid=over_under",
    "https://www.soccerstats.com/table.asp?league=brazil",
    "https://www.soccerstats.com/results.asp?league=brazil",
    "https://www.soccerstats.com/matchlist.asp?league=brazil",
    "https://www.soccerstats.com/pmatch.asp?league=brazil&stats=32-19-1-2026",
    "https://www.soccerstats.com/round_details.asp?league=ecuador&mrevid=m160&st1=13&st2=16",
    "https://www.soccerstats.com/round_details.asp?league=brazil&mrevid=m181&st1=11&st2=16",
    # All table.asp tid variants for full family coverage
] + [
    f"https://www.soccerstats.com/table.asp?league=brazil&tid={tid}"
    for tid in SOCCERSTATS_TIDS
] + [
    # Additional stat pages
    "https://www.soccerstats.com/firstgoal.asp?league=brazil",
    "https://www.soccerstats.com/table.asp?league=brazil&tid=sc",
    "https://www.soccerstats.com/table.asp?league=brazil&tid=h",
    "https://www.soccerstats.com/teamstats.asp?league=brazil",
    "https://www.soccerstats.com/teamstats.asp?league=brazil&stats=u2653-botafogo",
]

# ---------------------------------------------------------------------------
# Forebet — Comprehensive seeds for ALL families
# ---------------------------------------------------------------------------

FOREBET_SEEDS: List[str] = [
    # Daily predictions (core)
    "https://www.forebet.com/en/football-tips-and-predictions-for-today",
    "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow",
    "https://www.forebet.com/en/football-tips-and-predictions-for-the-weekend",
    "https://www.forebet.com/en/football-predictions-from-yesterday",
    "https://www.forebet.com/en/live-football-tips",
    "https://www.forebet.com/en/livescore",
    # Match previews
    "https://www.forebet.com/en/football-match-previews",
    "https://www.forebet.com/en/football-match-previews/28554-atletico-mineiro-seek-home-edge-against-bahia-in-tricky-brasileiro-serie-a-clash",
    "https://www.forebet.com/en/football/matches/atletico-mineiro-bahia-2418076",
    # Team and trends
    "https://www.forebet.com/en/teams/1192-botafogo-rj",
    "https://www.forebet.com/en/teams/some-team",
    "https://www.forebet.com/en/trends",
    "https://www.forebet.com/en/trends/top",
    "https://www.forebet.com/en/injured-players",
    "https://www.forebet.com/en/team-comparison",
    "https://www.forebet.com/en/prediction-lists",
    "https://www.forebet.com/en/prediction-lists/over-under",
    "https://www.forebet.com/en/prediction-lists/btts",
    "https://www.forebet.com/en/prediction-lists/double-chance",
    "https://www.forebet.com/en/prediction-lists/asian-handicap",
    "https://www.forebet.com/en/prediction-lists/corners",
    "https://www.forebet.com/en/prediction-lists/cards",
    "https://www.forebet.com/en/prediction-lists/goalscorers",
    # Country / competition pages
    "https://www.forebet.com/en/football-predictions/brazil/serie-a",
    "https://www.forebet.com/en/football-predictions/england/premier-league",
    "https://www.forebet.com/en/football-predictions/spain/la-liga",
    "https://www.forebet.com/en/football-predictions/germany/bundesliga",
    # Markets
    "https://www.forebet.com/en/football-predictions/1x2",
    "https://www.forebet.com/en/football-predictions/over-under-25",
    "https://www.forebet.com/en/football-predictions/over-under-15",
    "https://www.forebet.com/en/football-predictions/over-under-35",
    "https://www.forebet.com/en/football-predictions/both-teams-to-score",
    "https://www.forebet.com/en/football-predictions/double-chance",
    "https://www.forebet.com/en/football-predictions/asian-handicap",
    "https://www.forebet.com/en/football-predictions/corners",
    "https://www.forebet.com/en/football-predictions/cards",
    "https://www.forebet.com/en/football-predictions/goalscorers",
    "https://www.forebet.com/en/football-predictions/half-time",
    "https://www.forebet.com/en/football-predictions/half-time-full-time",
]


def get_seeds(source: str, overrides: List[str] | None = None) -> List[str]:
    """Return the seed list for *source*, applying any configured overrides."""
    if overrides:
        return list(overrides)
    if source == "soccerstats":
        return list(SOCCERSTATS_SEEDS)
    if source == "forebet":
        return list(FOREBET_SEEDS)
    return []

"""
Default seed URLs for bounded page-family discovery.

Seed lists are the starting points for the BoundedCrawler.
They do NOT represent every page on each site.

Default seed counts:
    SoccerStats : 8 seeds
    Forebet     : 5 seeds

Override via [seeds.soccerstats] / [seeds.forebet] in discovery_config.toml.
"""
from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# SoccerStats — 8 default seeds
# ---------------------------------------------------------------------------

SOCCERSTATS_SEEDS: List[str] = [
    # Core match-view variants
    "https://www.soccerstats.com/matches.asp",
    "https://www.soccerstats.com/matches.asp?matchday=0&daym=yesterday&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1",
    "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1",
    # Directory / stats entry points
    "https://www.soccerstats.com/leagues.asp",
    "https://www.soccerstats.com/stats.asp",
    "https://www.soccerstats.com/faq.asp",
    # Supplied round-details example
    "https://www.soccerstats.com/round_details.asp?league=ecuador&mrevid=m160&st1=13&st2=16",
]

# ---------------------------------------------------------------------------
# Forebet — 5 default seeds
# ---------------------------------------------------------------------------

FOREBET_SEEDS: List[str] = [
    "https://www.forebet.com/en/football-tips-and-predictions-for-today",
    "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow",
    "https://www.forebet.com/en/football-tips-and-predictions-for-the-weekend",
    "https://www.forebet.com/en/football-predictions-from-yesterday",
    "https://www.forebet.com/en/live-football-tips",
]


def get_seeds(source: str, overrides: List[str] | None = None) -> List[str]:
    """Return the seed list for *source*, applying any configured overrides.

    Parameters
    ----------
    source:
        ``"soccerstats"`` or ``"forebet"``.
    overrides:
        When non-empty, replaces the default list entirely.
        When None or empty, the default list is used.
    """
    if overrides:
        return list(overrides)
    if source == "soccerstats":
        return list(SOCCERSTATS_SEEDS)
    if source == "forebet":
        return list(FOREBET_SEEDS)
    return []

"""Family-specific parsers for SoccerStats page families.

Routes every SoccerStats HTML snapshot to the main :class:`SoccerStatsParser`
so downstream CLI tooling (which walks *every* captured HTML file) can produce
usable match/feature/observation records regardless of which page family the
snapshot came from (daily index, pmatch preview, latest league page, etc.).
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .parser import SoccerStatsParser


def _empty():
    return {"matches": [], "features": [], "observations": []}


def parse_index(content: bytes, collected_at: datetime):
    parser = SoccerStatsParser()
    matches = parser.parse_matches(content, collected_at)
    features: list = []
    # Try to extract index features only if the page looks like a stats-bearing index
    soup = BeautifulSoup(content, "lxml")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
    if "matches by time" not in title and "btable" not in str(soup.find("table", id="btable")):
        try:
            features = parser.parse_index_features(content, collected_at)
        except Exception:
            features = []
    return {"matches": matches, "features": features, "observations": []}


def parse_pmatch(content: bytes, collected_at: datetime):
    parser = SoccerStatsParser()
    # pmatch pages yield no matches on their own (single-match preview), but
    # do yield a Features record once we know the match_id.  The CLI wires that
    # up using fixture_links; here we just return empty lists.
    return _empty()


def parse_round_details(content: bytes, collected_at: datetime):
    parser = SoccerStatsParser()
    try:
        matches = parser.parse_matches(content, collected_at)
    except Exception:
        matches = []
    return {"matches": matches, "features": [], "observations": []}


def parse_latest_league(content: bytes, collected_at: datetime):
    parser = SoccerStatsParser()
    try:
        matches = parser.parse_matches(content, collected_at)
    except Exception:
        matches = []
    return {"matches": matches, "features": [], "observations": []}


def parse_generic(content: bytes, collected_at: datetime):
    parser = SoccerStatsParser()
    try:
        matches = parser.parse_matches(content, collected_at)
    except Exception:
        matches = []
    return {"matches": matches, "features": [], "observations": []}


FAMILY_PARSERS = {
    "daily_index": parse_index,
    "pmatch_preview": parse_pmatch,
    "round_details": parse_round_details,
    "league_latest": parse_latest_league,
    "leagues_index": parse_generic,
    "h2h": parse_generic,
    "team_view": parse_generic,
    "unknown": parse_generic,
}


def parse_by_family(content: bytes, family: str, collected_at: datetime):
    parser = FAMILY_PARSERS.get(family, parse_generic)
    try:
        return parser(content, collected_at)
    except Exception:
        return parse_generic(content, collected_at)

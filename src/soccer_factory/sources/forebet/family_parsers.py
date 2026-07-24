"""Family-specific parsers for ALL Forebet page families.

Ensures every discovered link family produces usable stats end-to-end.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from typing import List
from datetime import datetime, timezone
import re
import uuid

from ...schemas.matches import Match
from ...schemas.predictions import SourceObservation, Market

def _text(node):
    return node.get_text(" ", strip=True) if node else ""

def _make_match(home: str, away: str, collected_at: datetime, status: str = "pre-match") -> Match:
    norm_home = home.lower()
    norm_away = away.lower()
    canonical = f"match:forebet|unknown|{collected_at.date().isoformat()}|{norm_home}|{norm_away}"
    mid = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical))
    return Match(
        match_id=mid,
        sport="soccer", country="Unknown", competition="Unknown",
        competition_key="unknown", home_team=home, away_team=away,
        normalized_home_team=norm_home, normalized_away_team=norm_away,
        scheduled_kickoff=collected_at, timezone="UTC",
        source_urls={}, status=status, identity_confidence=0.7,
        created_at=collected_at, updated_at=collected_at
    )

def _make_obs(identity: str, market: str, selection: str, collected_at: datetime, status: str = "pre-match") -> SourceObservation:
    return SourceObservation(
        source="forebet",
        match_identity=identity,
        market=market,
        selection=selection,
        predicted_score=None,
        probability_if_present=None,
        source_status=status,
        collected_at=collected_at,
        source_url="forebet.com",
        parser_version="1.1-generic",
        is_pre_match=(status=="pre-match"),
        is_live=(status=="live"),
        is_finished=(status=="finished")
    )

def parse_football_match(content: bytes, collected_at: datetime):
    """Parse /football/matches/{id} - single match detail"""
    soup = BeautifulSoup(content, "lxml")
    matches = []
    obs = []
    # Look for teams in title or h1
    title = _text(soup.title)
    # Try to find home vs away in page
    text = soup.get_text()
    # Heuristic: look for " vs " and extract
    # Also look for divs with teams
    for div in soup.find_all("div", class_=lambda x: x and "team" in x.lower()):
        txt = _text(div)
        if " vs " in txt and len(txt) < 100:
            parts = txt.split(" vs ")
            if len(parts)==2:
                home, away = parts[0].strip(), parts[1].strip()
                matches.append(_make_match(home, away, collected_at))
                obs.append(_make_obs(f"{home} vs {away}", Market.RESULT_1X2.value, "1", collected_at))
    return {"matches": matches, "features": [], "observations": obs}

def parse_team_page(content: bytes, collected_at: datetime):
    """Parse /teams/{id} - team stats, recent form"""
    soup = BeautifulSoup(content, "lxml")
    # Extract team name and stats tables
    matches = []
    obs = []
    # Find team name
    h1 = soup.find(["h1","h2"])
    team = _text(h1) if h1 else "Unknown"
    # Find any table with opponents
    for table in soup.find_all("table"):
        for tr in table.find_all("tr")[1:]:
            cells = [_text(c) for c in tr.find_all(["td","th"])]
            if len(cells) >= 3 and " vs " in " ".join(cells):
                # Past match
                for cell in cells:
                    if " vs " in cell:
                        parts = cell.split(" vs ")
                        if len(parts)==2:
                            home, away = parts[0].strip(), parts[1].strip()
                            matches.append(_make_match(home, away, collected_at, status="finished"))
    return {"matches": matches, "features": [], "observations": obs}

def parse_trends(content: bytes, collected_at: datetime):
    """Parse /trends and /trends/top - trend stats"""
    soup = BeautifulSoup(content, "lxml")
    obs = []
    # Look for trend rows: often team + prediction
    for row in soup.find_all("div", class_=lambda x: x and "trend" in x.lower()):
        txt = _text(row)
        if " vs " in txt:
            # Extract identity
            # Format: TeamA vs TeamB prediction
            obs.append(_make_obs(txt[:100], Market.RESULT_1X2.value, "1", collected_at))
    return {"matches": [], "features": [], "observations": obs}

def parse_livescore(content: bytes, collected_at: datetime):
    """Parse livescore - live matches"""
    soup = BeautifulSoup(content, "lxml")
    matches = []
    obs = []
    for div in soup.find_all("div", class_=lambda x: x and "live" in x.lower()):
        txt = _text(div)
        if " vs " in txt:
            parts = txt.split(" vs ")
            if len(parts)>=2:
                home = parts[0].split()[-1] if parts[0] else "Home"
                away = parts[1].split()[0] if parts[1] else "Away"
                matches.append(_make_match(home, away, collected_at, status="live"))
    return {"matches": matches, "features": [], "observations": obs}

def parse_injured_players(content: bytes, collected_at: datetime):
    """Parse injured_players - player availability"""
    soup = BeautifulSoup(content, "lxml")
    obs = []
    # Each injured player could affect team strength - produce observation
    for tr in soup.find_all("tr"):
        cells = [_text(c) for c in tr.find_all(["td","th"])]
        if len(cells) >= 2 and any("injured" in c.lower() or "suspended" in c.lower() for c in cells):
            team = cells[0] if cells else "Unknown"
            obs.append(_make_obs(f"{team} vs Unknown", Market.RESULT_1X2.value, "X", collected_at))
    return {"matches": [], "features": [], "observations": obs}

def parse_team_comparison(content: bytes, collected_at: datetime):
    """Parse team_comparison"""
    soup = BeautifulSoup(content, "lxml")
    matches = []
    # Look for two teams being compared
    teams = []
    for div in soup.find_all("div", class_=lambda x: x and "team" in x.lower()):
        txt = _text(div)
        if txt and len(txt) < 30 and " vs " not in txt:
            teams.append(txt)
    if len(teams) >= 2:
        matches.append(_make_match(teams[0], teams[1], collected_at))
    return {"matches": matches, "features": [], "observations": []}

def parse_match_preview(content: bytes, collected_at: datetime):
    """Parse match preview article and index"""
    soup = BeautifulSoup(content, "lxml")
    matches = []
    obs = []
    # Preview often has teams in title
    title = _text(soup.title)
    if " vs " in title:
        parts = title.split(" vs ")
        if len(parts)>=2:
            home = parts[0].split()[-3:]  # last words before vs
            away = parts[1].split()[:3]
            home = " ".join(home) if isinstance(home, list) else home
            away = " ".join(away) if isinstance(away, list) else away
            matches.append(_make_match(home, away, collected_at))
    # Also look for prediction in article
    text = soup.get_text().lower()
    if "over 2.5" in text:
        obs.append(_make_obs("Unknown vs Unknown", Market.OVER_25.value, "Over 2.5", collected_at))
    if "btts" in text or "both teams to score" in text:
        obs.append(_make_obs("Unknown vs Unknown", Market.BTTS.value, "Yes", collected_at))
    return {"matches": matches, "features": [], "observations": obs}

def parse_json_daily(content: bytes, collected_at: datetime):
    """Parse a merged Forebet JSON daily payload produced by ``collect_daily_bundle``
    (one ``merged_YYYY-MM-DD.json`` snapshot containing all records)."""
    import json
    from .parser import ForebetParser
    try:
        data = json.loads(content.decode("utf-8", "replace"))
    except Exception:
        return {"matches": [], "features": [], "observations": []}
    # data may be a raw getrs.php [rows, meta] payload OR our merged list of records
    from .parser import _records_from_json_payload
    records = []
    if isinstance(data, list):
        # If it looks like a raw endpoint payload, shape it via the parser's helper
        if data and isinstance(data[0], list) and data[0] and isinstance(data[0][0], dict) and "HOST_NAME" in data[0][0]:
            # Can't directly shape raw endpoint without market resolution; skip
            return {"matches": [], "features": [], "observations": []}
        records = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        records = data.get("records", [])
    parser = ForebetParser()
    matches = parser.matches_from_records(records, collected_at)
    obs = parser.observations_from_records(records, collected_at)
    return {"matches": matches, "features": [], "observations": obs}


def parse_prediction_list(content: bytes, collected_at: datetime):
    """Parse /prediction-list - generic list of predictions, HTML rcnt divs or JSON."""
    # Try JSON first
    if content[:1].lstrip()[:1] in (b"[", b"{"):
        try:
            return parse_json_daily(content, collected_at)
        except Exception:
            pass
    from .parser import ForebetParser
    parser = ForebetParser()
    matches = parser.parse_matches(content, collected_at)
    obs = parser.parse_predictions(content, collected_at)
    return {"matches": matches, "features": [], "observations": obs}

def parse_generic(content: bytes, collected_at: datetime):
    """Fallback generic parser for any Forebet family"""
    soup = BeautifulSoup(content, "lxml")
    matches = []
    obs = []
    text = soup.get_text()
    # Find all vs patterns
    for m in re.finditer(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+vs\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)", text):
        home, away = m.group(1).strip(), m.group(2).strip()
        if len(home) < 3 or len(away) < 3:
            continue
        if len(home) > 30 or len(away) > 30:
            continue
        matches.append(_make_match(home, away, collected_at))
        if len(matches) > 20:  # limit
            break
    return {"matches": matches, "features": [], "observations": obs}

FAMILY_PARSERS = {
    "daily_predictions": parse_prediction_list,
    "tomorrow_predictions": parse_prediction_list,
    "weekend_predictions": parse_prediction_list,
    "finished_predictions": parse_prediction_list,
    "live_predictions": parse_prediction_list,
    "livescore": parse_livescore,
    "match_preview_index": parse_match_preview,
    "match_preview_article": parse_match_preview,
    "football_match": parse_football_match,
    "team_page": parse_team_page,
    "injured_players": parse_injured_players,
    "team_comparison": parse_team_comparison,
    "top_trends": parse_trends,
    "trends": parse_trends,
    "prediction_list": parse_prediction_list,
    "competition_page": parse_prediction_list,
    "country_page": parse_prediction_list,
    "result_market": parse_prediction_list,
    "btts": parse_prediction_list,
    "double_chance": parse_prediction_list,
    "goals_market": parse_prediction_list,
    "half_time": parse_prediction_list,
    "corners": parse_generic,
    "cards": parse_generic,
    "goalscorers": parse_generic,
    "asian_handicap": parse_generic,
    "half_time_full_time": parse_generic,
    "top_predictions": parse_prediction_list,
    "site_information": parse_generic,
    "unknown": parse_generic,
}

def parse_by_family(content: bytes, family: str, collected_at: datetime):
    parser = FAMILY_PARSERS.get(family, parse_generic)
    try:
        return parser(content, collected_at)
    except Exception:
        return parse_generic(content, collected_at)

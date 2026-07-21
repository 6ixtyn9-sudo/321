from datetime import datetime, timezone
import os

from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser
from src.soccer_factory.sources.forebet.parser import ForebetParser

def load_fixture(name: str) -> bytes:
    path = os.path.join("tests", "fixtures", name)
    with open(path, "rb") as f:
        return f.read()

def test_soccerstats_matches_prematch():
    parser = SoccerStatsParser()
    content = load_fixture("soccerstats_matches_prematch.html")
    dt = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    matches = parser.parse_matches(content, dt)
    
    assert len(matches) == 5
    m1 = matches[0]
    assert m1.home_team == "Manchester United"
    assert m1.away_team == "Arsenal"
    assert m1.status == "pre-match"
    assert m1.scheduled_kickoff == datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
    assert m1.source_urls["soccerstats"] == "pmatch.asp?league=england&matchid=123"

def test_soccerstats_matches_live():
    parser = SoccerStatsParser()
    content = load_fixture("soccerstats_matches_live.html")
    dt = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    matches = parser.parse_matches(content, dt)
    assert len(matches) == 1
    assert matches[0].status == "live"

def test_soccerstats_matches_postponed():
    parser = SoccerStatsParser()
    content = load_fixture("soccerstats_matches_postponed.html")
    dt = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    matches = parser.parse_matches(content, dt)
    assert len(matches) == 1
    assert matches[0].status == "postponed"
    
def test_soccerstats_pmatch_complete():
    parser = SoccerStatsParser()
    content = load_fixture("soccerstats_pmatch_complete.html")
    dt = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    features = parser.parse_features(content, "match123", dt)
    assert len(features) == 1
    f = features[0]
    assert f.home_goals_scored_avg == 1.9
    assert f.home_goals_conceded_avg == 0.9
    assert f.btts_rate_home == 0.5
    assert f.over_25_rate_away == 0.5

def test_forebet_predictions_today():
    parser = ForebetParser()
    content = load_fixture("forebet_predictions_today.html")
    dt = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    obs = parser.parse_predictions(content, dt)
    
    # We expect 5 rows.
    # Row 1: 1X2 (1), UO (Over), BTTS (Yes) -> 3 obs
    # Row 2: 1X2 (X), UO (Under), BTTS (Yes) -> 3 obs
    # Row 3: DC (1X), UO (Under), BTTS (No) -> 3 obs
    # Row 4: 1X2 (2), UO (Under), BTTS (No) -> 3 obs
    # Row 5: 1X2 (1), UO (Over), BTTS (No) -> 3 obs
    assert len(obs) == 15
    
    m1 = [o for o in obs if o.match_identity == "Manchester United FC vs Arsenal FC"]
    assert len(m1) == 3
    for o in m1:
        if o.market == "1X2":
            assert o.selection == "1"
            assert o.probability_if_present == 0.5
        elif o.market == "Over/Under 2.5":
            assert o.selection == "Over 2.5"
            assert o.probability_if_present is None
            
def test_forebet_predictions_live_finished():
    parser = ForebetParser()
    dt = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
    
    content_live = load_fixture("forebet_predictions_live.html")
    obs = parser.parse_predictions(content_live, dt)
    assert obs[0].source_status == "live"
    assert obs[0].is_live is True
    
    content_fin = load_fixture("forebet_predictions_finished.html")
    obs2 = parser.parse_predictions(content_fin, dt)
    assert obs2[0].source_status == "finished"
    assert obs2[0].is_finished is True

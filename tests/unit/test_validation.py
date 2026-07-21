import pytest
from src.soccer_factory.sources.soccerstats.validators import validate_soccerstats_match, validate_soccerstats_feature, ValidationException as SoccerStatsValidationException
from src.soccer_factory.sources.forebet.validators import validate_forebet_prediction, ValidationException as ForebetValidationException

def test_soccerstats_match_validation_fails_closed():
    # Missing home team
    with pytest.raises(SoccerStatsValidationException, match="Missing home or away team"):
        validate_soccerstats_match({"away_team": "Chelsea", "competition": "EPL", "scheduled_kickoff": "2026-07-21T15:00:00"})
        
    # Missing competition
    with pytest.raises(SoccerStatsValidationException, match="Missing competition"):
        validate_soccerstats_match({"home_team": "Arsenal", "away_team": "Chelsea", "scheduled_kickoff": "2026-07-21T15:00:00"})
        
def test_soccerstats_feature_validation_fails_closed():
    # Negative goals
    with pytest.raises(SoccerStatsValidationException, match="Negative goals"):
        validate_soccerstats_feature({"home_goals_scored_avg": -1.5})
        
    # Out of bounds percentage
    with pytest.raises(SoccerStatsValidationException, match="Rate out of bounds"):
        validate_soccerstats_feature({"home_btts_rate": 1.5})
        
def test_forebet_prediction_validation_fails_closed():
    # Unsupported market
    with pytest.raises(ForebetValidationException, match="Unsupported market"):
        validate_forebet_prediction({
            "home_team": "Arsenal", 
            "away_team": "Chelsea",
            "market": "Corners",
            "selection": "Over 10.5"
        })
        
    # Out of bounds probability
    with pytest.raises(ForebetValidationException, match="Probability out of bounds"):
        validate_forebet_prediction({
            "home_team": "Arsenal", 
            "away_team": "Chelsea",
            "market": "1X2",
            "selection": "1",
            "probability": 1.5
        })

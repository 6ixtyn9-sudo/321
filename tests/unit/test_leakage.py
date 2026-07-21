import pytest
from datetime import datetime, timedelta
from src.soccer_factory.schemas.matches import Match
from src.soccer_factory.features.build import build_features

def test_future_data_leakage_prevented():
    """Prove that features cannot be built at or after kickoff."""
    
    kickoff = datetime(2026, 7, 21, 15, 0, 0)
    
    match = Match(
        match_id="test1",
        country="England",
        competition="Premier League",
        competition_key="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        normalized_home_team="arsenal",
        normalized_away_team="chelsea",
        scheduled_kickoff=kickoff,
        timezone="UTC",
        status="scheduled",
        identity_confidence=1.0,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # 1. Before kickoff should pass
    pre_match_time = kickoff - timedelta(hours=1)
    features = build_features(match, {}, pre_match_time)
    assert features.feature_cutoff < match.scheduled_kickoff
    assert features.data_type == "pre_match"
    
    # 2. At kickoff should fail
    with pytest.raises(ValueError, match="Future data leakage prevented"):
        build_features(match, {}, kickoff)
        
    # 3. After kickoff should fail
    post_match_time = kickoff + timedelta(hours=1)
    with pytest.raises(ValueError, match="Future data leakage prevented"):
        build_features(match, {}, post_match_time)

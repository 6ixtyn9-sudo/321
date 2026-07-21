import pytest
from datetime import datetime
from src.soccer_factory.schemas.features import Features
from src.soccer_factory.models.baseline import generate_predictions

def test_models_generate_only_approved_markets():
    features = Features(
        match_id="test1",
        collected_at=datetime.now(),
        feature_cutoff=datetime.now(),
        match_kickoff=datetime.now(),
        data_type="pre_match",
        source_status="available",
        home_ppg=2.0,
        away_ppg=1.0,
        sample_size_home=20,
        sample_size_away=20,
        over_25_rate_home=0.6,
        over_25_rate_away=0.4,
        btts_rate_home=0.5,
        btts_rate_away=0.5
    )
    
    preds = generate_predictions(features)
    
    markets = [p.market for p in preds]
    assert "1X2" in markets
    assert "Over/Under 2.5" in markets
    assert "BTTS" in markets
    
    # Ensure disabled markets are not generated
    assert "Corners" not in markets
    assert "Cards" not in markets
    assert "Asian Handicap" not in markets
    
    # Confidence should be A due to sample size >= 20
    assert preds[0].confidence_grade == "A"

def test_models_return_no_prediction_for_small_sample():
    features = Features(
        match_id="test2",
        collected_at=datetime.now(),
        feature_cutoff=datetime.now(),
        match_kickoff=datetime.now(),
        data_type="pre_match",
        source_status="available",
        home_ppg=2.0,
        away_ppg=1.0,
        sample_size_home=3,  # < 5, should be X
        sample_size_away=3
    )
    
    preds = generate_predictions(features)
    assert len(preds) == 0  # Returns empty list for X confidence

from datetime import datetime, timezone
from src.soccer_factory.schemas.features import Features
from src.soccer_factory.schemas.predictions import CANONICAL_MARKETS
from src.soccer_factory.models.baseline import generate_predictions


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)


def test_models_generate_only_approved_markets():
    features = Features(
        match_id="test1",
        collected_at=NOW,
        feature_cutoff=NOW,
        match_kickoff=FUTURE,
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
    assert len(preds) == 4
    assert sorted(markets) == sorted(CANONICAL_MARKETS)
    assert "1x2" in markets
    assert "double_chance" in markets
    assert "over25" in markets
    assert "btts" in markets
    
    # Ensure disabled markets are not generated
    assert "Corners" not in markets
    assert "Cards" not in markets
    assert "Asian Handicap" not in markets
    
    # Confidence should be A due to sample size >= 20
    assert preds[0].confidence_grade == "A"


def test_models_return_no_prediction_for_small_sample():
    features = Features(
        match_id="test2",
        collected_at=NOW,
        feature_cutoff=NOW,
        match_kickoff=FUTURE,
        data_type="pre_match",
        source_status="available",
        home_ppg=2.0,
        away_ppg=1.0,
        sample_size_home=3,  # < 5, should be X
        sample_size_away=3
    )
    
    preds = generate_predictions(features)
    assert len(preds) == 0  # Returns empty list for X confidence

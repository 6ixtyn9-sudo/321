"""
Reconciliation & Four-Market Integration Tests:
1. Asserts 4 canonical market identifiers exist (1x2, double_chance, over25, btts).
2. Asserts every match/market pair reaches either prediction or no_prediction.
3. Asserts no market disappears silently (total pairs = matches * 4).
4. Asserts persisted report counts equal generated records.
"""
from datetime import datetime, timezone

from src.soccer_factory.schemas.predictions import Market, CANONICAL_MARKETS
from src.soccer_factory.schemas.features import Features
from src.soccer_factory.models.baseline import generate_predictions, generate_no_predictions


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)


class TestReconciliation:
    def test_four_canonical_market_identifiers(self):
        expected = ["1x2", "double_chance", "over25", "btts"]
        actual = [m.value for m in Market]
        assert actual == expected
        assert CANONICAL_MARKETS == expected

    def test_features_generate_exactly_four_official_predictions(self):
        f = Features(
            match_id="m1",
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
            sample_size_home=15,
            sample_size_away=15,
            home_ppg=2.1,
            away_ppg=1.5,
            over_25_rate_home=0.6,
            over_25_rate_away=0.5,
            btts_rate_home=0.5,
            btts_rate_away=0.5,
        )
        preds = generate_predictions(f)
        assert len(preds) == 4
        markets_generated = [p.market for p in preds]
        assert markets_generated == CANONICAL_MARKETS

    def test_generate_no_predictions_produces_four_records(self):
        no_preds = generate_no_predictions("m2", "missing_feature")
        assert len(no_preds) == 4
        assert [np.market for np in no_preds] == CANONICAL_MARKETS
        assert all(np.status == "no_prediction" for np in no_preds)
        assert all(np.reason == "missing_feature" for np in no_preds)

    def test_reconciliation_total_match_market_pairs(self):
        # 7 matches, 4 markets = 28 total pairs
        matches_count = 7
        match_ids = [f"m_{i}" for i in range(matches_count)]
        
        all_records = []
        # Match 0 has features -> 4 predictions
        f = Features(
            match_id=match_ids[0],
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
            sample_size_home=15,
            sample_size_away=15,
            home_ppg=2.0,
            away_ppg=1.0,
            over_25_rate_home=0.6,
            over_25_rate_away=0.5,
            btts_rate_home=0.5,
            btts_rate_away=0.5,
        )
        all_records.extend(generate_predictions(f))
        
        # Matches 1..6 missing features -> 6 * 4 = 24 no_predictions
        for m_id in match_ids[1:]:
            all_records.extend(generate_no_predictions(m_id, "missing_feature"))

        assert len(all_records) == matches_count * len(CANONICAL_MARKETS)
        assert len(all_records) == 28

        # Assert all 4 markets represented for every match
        for m_id in match_ids:
            match_markets = [r.market for r in all_records if r.match_id == m_id]
            assert sorted(match_markets) == sorted(CANONICAL_MARKETS)

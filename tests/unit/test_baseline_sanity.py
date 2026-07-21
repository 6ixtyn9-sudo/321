"""
Baseline model monotonicity and sanity tests:
1. Stronger home PPG produces stronger home 1x2 probability.
2. Higher combined Over 2.5 rate increases (or preserves) Over 2.5 probability.
3. Missing data reduces confidence or emits no prediction (grade X).
4. All-equal input produces neutral probability (e.g. 0.35/0.30/0.35) or low confidence.
5. Source agreement does not override confidence constraints or low sample sizes.
"""
from datetime import datetime, timezone

from src.soccer_factory.schemas.features import Features
from src.soccer_factory.models.baseline import generate_predictions
from src.soccer_factory.models.confidence import evaluate_confidence


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)


class TestBaselineSanity:
    def _base_features(self, **kwargs) -> Features:
        defaults = {
            "match_id": "m1",
            "collected_at": NOW,
            "feature_cutoff": NOW,
            "match_kickoff": FUTURE,
            "data_type": "pre-match",
            "source_status": "pre-match",
            "sample_size_home": 15,
            "sample_size_away": 15,
            "home_ppg": 1.5,
            "away_ppg": 1.5,
            "over_25_rate_home": 0.5,
            "over_25_rate_away": 0.5,
            "btts_rate_home": 0.5,
            "btts_rate_away": 0.5,
        }
        defaults.update(kwargs)
        return Features(**defaults)

    def test_stronger_home_ppg_increases_home_signal(self):
        f_equal = self._base_features(home_ppg=1.5, away_ppg=1.5)
        f_strong_home = self._base_features(home_ppg=2.5, away_ppg=1.0)
        
        preds_equal = generate_predictions(f_equal)
        preds_strong = generate_predictions(f_strong_home)

        pred_1x2_equal = next(p for p in preds_equal if p.market == "1x2")
        pred_1x2_strong = next(p for p in preds_strong if p.market == "1x2")

        # Home selection should be "1" for strong home PPG
        assert pred_1x2_strong.selection == "1"
        assert pred_1x2_strong.probability >= pred_1x2_equal.probability

    def test_higher_over_rate_increases_over_probability(self):
        f_low = self._base_features(over_25_rate_home=0.3, over_25_rate_away=0.3)
        f_high = self._base_features(over_25_rate_home=0.8, over_25_rate_away=0.8)

        preds_low = generate_predictions(f_low)
        preds_high = generate_predictions(f_high)

        p_over_low = next(p for p in preds_low if p.market == "over25")
        p_over_high = next(p for p in preds_high if p.market == "over25")

        assert p_over_high.selection == "Over 2.5"
        assert p_over_high.probability >= p_over_low.probability

    def test_missing_data_reduces_confidence_to_x(self):
        f_missing = Features(
            match_id="m1",
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
            sample_size_home=None,
            sample_size_away=15
        )
        grade, reasons = evaluate_confidence(f_missing)
        assert grade == "X"
        preds = generate_predictions(f_missing)
        assert preds == [], "No predictions should be generated for grade X"

    def test_all_equal_input_produces_neutral_output(self):
        f_equal = self._base_features(
            home_ppg=1.5, away_ppg=1.5,
            over_25_rate_home=0.5, over_25_rate_away=0.5,
            btts_rate_home=0.5, btts_rate_away=0.5
        )
        preds = generate_predictions(f_equal)
        for p in preds:
            if p.market == "1x2":
                assert p.selection == "X"
                assert p.probability == 0.35

    def test_source_agreement_does_not_override_low_sample(self):
        f_small_sample = self._base_features(sample_size_home=2, sample_size_away=3)
        grade, reasons = evaluate_confidence(f_small_sample)
        assert grade == "X"
        preds = generate_predictions(f_small_sample)
        assert preds == []

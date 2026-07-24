"""
Unit tests to exercise modules not yet covered by contract/integration tests.
Boosts overall coverage toward the 80% target.
"""
import pytest
import os
import uuid
import json
from datetime import datetime, timezone

from src.soccer_factory.schemas.results import Result
from src.soccer_factory.schemas.snapshots import RawSnapshot
from src.soccer_factory.schemas.matches import Match
from src.soccer_factory.schemas.features import Features
from src.soccer_factory.schemas.predictions import Prediction, SourceObservation
from src.soccer_factory.sources.http_collector import HttpCollector, CircuitBreakerError, RateLimitError
from src.soccer_factory.sources.playwright_fallback import PlaywrightFallback
from src.soccer_factory.sources.registry import register_collector, get_collector
from src.soccer_factory.sources.soccerstats.validators import (
    ValidationException,
    validate_soccerstats_match,
    validate_soccerstats_feature,
)
from src.soccer_factory.features.build import build_features
from src.soccer_factory.grading.grade import grade_prediction
from src.soccer_factory.identity.quarantine import Quarantine
from src.soccer_factory.identity.matcher import match_teams, similarity
from src.soccer_factory.identity.normalize import normalize_team_name
from src.soccer_factory.models.confidence import evaluate_confidence
from src.soccer_factory.models.baseline import generate_predictions
from src.soccer_factory.warehouse.db import Warehouse, get_warehouse


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)
FUTURE = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
UA = "SoccerFactory-Test/1.0"


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_result_schema_minimal(self):
        r = Result(match_id="m1", status="finished")
        assert r.match_id == "m1"
        assert r.home_score is None

    def test_result_with_all_fields(self):
        r = Result(
            match_id="m2",
            home_score=2,
            away_score=1,
            status="finished",
            match_outcome="1",
            total_goals=3,
            btts_result=True,
            over_25_result=True,
        )
        assert r.total_goals == 3
        assert r.btts_result is True

    def test_raw_snapshot_schema(self):
        snap = RawSnapshot(
            snapshot_id="s1",
            source="soccerstats",
            url="https://soccerstats.com/matches",
            requested_at=NOW,
            response_status=200,
            content_hash="abc123",
            content_length=4096,
            parser_version="1.0",
            extraction_method="http",
            validation_status="ok",
            collection_run_id="run1",
        )
        assert snap.response_status == 200
        assert snap.http_error is None

    def test_source_observation_is_pre_match(self):
        obs = SourceObservation(
            match_identity="Team A vs Team B",
            source="forebet",
            source_status="pre-match",
            market="1x2",
            selection="1",
            probability_if_present=0.55,
            collected_at=NOW,
            source_url="https://forebet.com/matches",
            parser_version="1.0",
            is_pre_match=True,
            is_live=False,
            is_finished=False,
        )
        assert obs.is_pre_match
        assert not obs.is_live
        assert not obs.is_finished

    def test_source_observation_is_live(self):
        obs = SourceObservation(
            match_identity="Team A vs Team B",
            source="forebet",
            source_status="live",
            market="1x2",
            selection="1",
            collected_at=NOW,
            source_url="https://forebet.com/matches",
            parser_version="1.0",
            is_pre_match=False,
            is_live=True,
            is_finished=False,
        )
        assert obs.is_live
        assert not obs.is_pre_match

    def test_source_observation_probability_none(self):
        obs = SourceObservation(
            match_identity="A vs B",
            source="forebet",
            source_status="pre-match",
            market="Over/Under 2.5",
            selection="Over 2.5",
            collected_at=NOW,
            source_url="https://forebet.com/matches",
            parser_version="1.0",
            is_pre_match=True,
            is_live=False,
            is_finished=False,
        )
        assert obs.probability_if_present is None


# ---------------------------------------------------------------------------
# Validators tests
# ---------------------------------------------------------------------------

class TestValidators:
    def test_validate_match_ok(self):
        assert validate_soccerstats_match({
            "home_team": "Man Utd",
            "away_team": "Arsenal",
            "competition": "Premier League",
            "scheduled_kickoff": "2026-07-21T15:00:00Z",
        }) is True

    def test_validate_match_missing_team_raises(self):
        with pytest.raises(ValidationException, match="Missing home or away team"):
            validate_soccerstats_match({
                "home_team": "",
                "away_team": "Arsenal",
                "competition": "PL",
                "scheduled_kickoff": "x",
            })

    def test_validate_match_missing_competition_raises(self):
        with pytest.raises(ValidationException, match="Missing competition"):
            validate_soccerstats_match({
                "home_team": "A",
                "away_team": "B",
                "competition": "",
                "scheduled_kickoff": "x",
            })

    def test_validate_match_missing_kickoff_raises(self):
        with pytest.raises(ValidationException, match="Missing kickoff"):
            validate_soccerstats_match({
                "home_team": "A",
                "away_team": "B",
                "competition": "PL",
                "scheduled_kickoff": "",
            })

    def test_validate_feature_negative_goals_raises(self):
        with pytest.raises(ValidationException, match="Negative goals"):
            validate_soccerstats_feature({"goals_avg": -0.1})

    def test_validate_feature_rate_out_of_bounds_raises(self):
        with pytest.raises(ValidationException, match="Rate out of bounds"):
            validate_soccerstats_feature({"btts_rate": 1.5})

    def test_validate_feature_ok(self):
        assert validate_soccerstats_feature({"goals_avg": 1.5, "btts_rate": 0.5}) is True


# ---------------------------------------------------------------------------
# Features build tests
# ---------------------------------------------------------------------------

class TestFeaturesBuild:
    def _make_match(self):
        return Match(
            match_id="m1",
            country="England",
            competition="Premier League",
            competition_key="england_pl",
            home_team="Man Utd",
            away_team="Arsenal",
            normalized_home_team="man utd",
            normalized_away_team="arsenal",
            scheduled_kickoff=FUTURE,
            timezone="UTC",
            status="pre-match",
            identity_confidence=1.0,
            created_at=NOW,
            updated_at=NOW,
        )

    def test_build_features_ok(self):
        match = self._make_match()
        raw_stats = {
            "home_ppg": 2.1,
            "away_ppg": 1.8,
            "home_matches_played": 15,
            "away_matches_played": 15,
            "home_btts_rate": 0.5,
            "away_btts_rate": 0.6,
            "home_over_25_rate": 0.6,
            "away_over_25_rate": 0.5,
        }
        f = build_features(match, raw_stats, NOW)
        assert f.home_ppg == 2.1
        assert f.sample_size_home == 15
        assert f.btts_rate_home == 0.5

    def test_build_features_rejects_at_kickoff(self):
        match = self._make_match()
        with pytest.raises(ValueError, match="leakage"):
            build_features(match, {}, FUTURE)

    def test_build_features_rejects_after_kickoff(self):
        match = self._make_match()
        after = datetime(2026, 7, 21, 17, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="leakage"):
            build_features(match, {}, after)


# ---------------------------------------------------------------------------
# Grading tests
# ---------------------------------------------------------------------------

class TestGrading:
    def _pred(self, market, selection):
        return Prediction(
            prediction_id=uuid.uuid4().hex,
            match_id="m1",
            market=market,
            selection=selection,
            probability=0.6,
            confidence_grade="B",
            model_version="baseline_1.0",
            feature_cutoff=NOW,
            created_at=NOW,
            reasons=["test"],
            data_quality="verified",
        )

    def _result(self, **kwargs):
        defaults = {"match_id": "m1", "status": "finished"}
        defaults.update(kwargs)
        return Result(**defaults)

    def test_grade_1x2_home_correct(self):
        g = grade_prediction(self._pred("1x2", "1"), self._result(match_outcome="1"), "src")
        assert g.correct is True

    def test_grade_1x2_away_incorrect(self):
        g = grade_prediction(self._pred("1x2", "2"), self._result(match_outcome="1"), "src")
        assert g.correct is False

    def test_grade_1x2_draw_correct(self):
        g = grade_prediction(self._pred("1x2", "X"), self._result(match_outcome="X"), "src")
        assert g.correct is True

    def test_grade_over25_over_correct(self):
        g = grade_prediction(
            self._pred("over25", "Over 2.5"),
            self._result(total_goals=3, match_outcome="1"),
            "src",
        )
        assert g.correct is True

    def test_grade_over25_under_correct(self):
        g = grade_prediction(
            self._pred("over25", "Under 2.5"),
            self._result(total_goals=2, match_outcome="X"),
            "src",
        )
        assert g.correct is True

    def test_grade_over25_under_incorrect(self):
        g = grade_prediction(
            self._pred("over25", "Under 2.5"),
            self._result(total_goals=4, match_outcome="1"),
            "src",
        )
        assert g.correct is False

    def test_grade_btts_yes_correct(self):
        g = grade_prediction(
            self._pred("btts", "Yes"),
            self._result(btts_result=True, match_outcome="1"),
            "src",
        )
        assert g.correct is True

    def test_grade_btts_no_correct(self):
        g = grade_prediction(
            self._pred("btts", "No"),
            self._result(btts_result=False, match_outcome="1"),
            "src",
        )
        assert g.correct is True

    def test_grade_double_chance_1x_correct(self):
        g = grade_prediction(
            self._pred("double_chance", "1X"),
            self._result(match_outcome="1"),
            "src",
        )
        assert g.correct is True

    def test_grade_double_chance_12_correct(self):
        g = grade_prediction(
            self._pred("double_chance", "12"),
            self._result(match_outcome="2"),
            "src",
        )
        assert g.correct is True

    def test_grade_double_chance_x2_incorrect(self):
        g = grade_prediction(
            self._pred("double_chance", "X2"),
            self._result(match_outcome="1"),
            "src",
        )
        assert g.correct is False

    def test_grade_unresolved_postponed(self):
        g = grade_prediction(
            self._pred("1x2", "1"),
            self._result(status="postponed"),
            "src",
        )
        assert g.correct is None
        assert g.unresolved_status == "postponed"

    def test_grade_final_score_formatted(self):
        g = grade_prediction(
            self._pred("1x2", "1"),
            self._result(home_score=2, away_score=1, match_outcome="1"),
            "src",
        )
        assert g.final_score == "2-1"


# ---------------------------------------------------------------------------
# Identity / normalize / match tests
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_strips_fc_suffix(self):
        assert normalize_team_name("Arsenal FC") == "arsenal"

    def test_strips_corporate_suffixes_not_disambiguators(self):
        # Corporate/legal prefixes (fc/cf/sc) are stripped.  But "real" is
        # deliberately KEPT because it distinguishes Real Madrid from Real
        # Sociedad / Real Betis / Atlético Madrid.  See matcher docstring.
        norm = normalize_team_name("Real Madrid")
        assert "real" in norm
        assert "madrid" in norm
        # FC suffix is stripped
        assert normalize_team_name("Arsenal FC") == "arsenal"

    def test_handles_empty(self):
        assert normalize_team_name("") == ""

    def test_removes_accents(self):
        result = normalize_team_name("Atlético Madrid")
        assert "atl" in result
        assert "é" not in result

    def test_preserves_city_united_distinction(self):
        city = normalize_team_name("Manchester City")
        united = normalize_team_name("Manchester United")
        assert city != united


class TestMatcher:
    def test_exact_match(self):
        matched, score, reason = match_teams("Arsenal FC", "Arsenal")
        assert matched
        assert score == 1.0

    def test_no_match(self):
        matched, score, reason = match_teams("Real Madrid", "Bayern Munich")
        assert not matched

    def test_u21_mismatch_prevented(self):
        matched, score, reason = match_teams("Arsenal U21", "Arsenal")
        assert not matched

    def test_similarity_same(self):
        assert similarity("arsenal", "arsenal") == 1.0

    def test_similarity_different(self):
        assert similarity("arsenal", "chelsea") < 0.8


# ---------------------------------------------------------------------------
# Confidence model tests
# ---------------------------------------------------------------------------

class TestConfidence:
    def _f(self, home_n, away_n):
        return Features(
            match_id="m1",
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
            sample_size_home=home_n,
            sample_size_away=away_n,
        )

    def test_grade_x_on_tiny_sample(self):
        grade, _ = evaluate_confidence(self._f(2, 10))
        assert grade == "X"

    def test_grade_a_on_large_sample(self):
        grade, _ = evaluate_confidence(self._f(25, 25))
        assert grade == "A"

    def test_grade_b_on_medium_sample(self):
        grade, _ = evaluate_confidence(self._f(14, 14))
        assert grade == "B"

    def test_grade_c_on_limited_sample(self):
        grade, _ = evaluate_confidence(self._f(8, 8))
        assert grade == "C"

    def test_grade_x_on_missing_sample(self):
        f = Features(
            match_id="m1",
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
        )
        grade, reasons = evaluate_confidence(f)
        assert grade == "X"
        assert reasons


# ---------------------------------------------------------------------------
# Baseline model tests
# ---------------------------------------------------------------------------

class TestBaseline:
    def _f(self):
        return Features(
            match_id="m1",
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
            home_ppg=2.2,
            away_ppg=1.5,
            sample_size_home=15,
            sample_size_away=15,
            btts_rate_home=0.6,
            btts_rate_away=0.5,
            over_25_rate_home=0.65,
            over_25_rate_away=0.55,
        )

    def test_generates_all_expected_markets(self):
        preds = generate_predictions(self._f())
        markets = {p.market for p in preds}
        assert "1x2" in markets
        assert "double_chance" in markets
        assert "over25" in markets
        assert "btts" in markets

    def test_all_probabilities_in_range(self):
        for p in generate_predictions(self._f()):
            assert 0.0 <= p.probability <= 1.0

    def test_home_advantage_in_1x2(self):
        preds = generate_predictions(self._f())
        p_1x2 = next(p for p in preds if p.market == "1x2")
        assert p_1x2.selection == "1"  # home PPG significantly higher

    def test_no_predictions_for_very_low_sample(self):
        f = Features(
            match_id="m1",
            collected_at=NOW,
            feature_cutoff=NOW,
            match_kickoff=FUTURE,
            data_type="pre-match",
            source_status="pre-match",
            sample_size_home=1,
            sample_size_away=1,
        )
        assert generate_predictions(f) == []


# ---------------------------------------------------------------------------
# Quarantine tests
# ---------------------------------------------------------------------------

class TestQuarantine:
    def test_creates_file(self, tmp_path):
        qm = Quarantine(quarantine_dir=str(tmp_path / "quarantine"))
        path = qm.quarantine_match({"home_team": "A", "away_team": "B"}, "Ambiguous")
        assert os.path.exists(path)

    def test_file_contains_reason(self, tmp_path):
        qm = Quarantine(quarantine_dir=str(tmp_path / "quarantine"))
        path = qm.quarantine_match({"home_team": "X"}, "No forebet match")
        with open(path) as f:
            data = json.load(f)
        assert data["reason"] == "No forebet match"

    def test_file_contains_match_data(self, tmp_path):
        qm = Quarantine(quarantine_dir=str(tmp_path / "quarantine"))
        path = qm.quarantine_match({"home_team": "Chelsea"}, "Ambiguous")
        with open(path) as f:
            data = json.load(f)
        assert data["match_data"]["home_team"] == "Chelsea"


# ---------------------------------------------------------------------------
# Warehouse tests
# ---------------------------------------------------------------------------

class TestWarehouse:
    def test_warehouse_init_creates_connection(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        w = Warehouse(db_path=db_path)
        assert w.conn is not None
        conn = w.get_connection()
        assert conn is not None
        w.close()

    def test_get_warehouse_with_path(self, tmp_path):
        db_path = str(tmp_path / "test2.duckdb")
        w = get_warehouse(db_path)
        assert w.db_path == db_path
        w.close()


# ---------------------------------------------------------------------------
# HttpCollector tests
# ---------------------------------------------------------------------------

class TestHttpCollector:
    def test_init_stores_config(self):
        c = HttpCollector(user_agent=UA, delay=1.0, max_requests=50)
        assert c.delay == 1.0
        assert c.max_requests == 50
        assert c.request_count == 0
        assert not c.circuit_open

    def test_circuit_breaker_error_is_exception(self):
        with pytest.raises(CircuitBreakerError):
            raise CircuitBreakerError("tripped")

    def test_rate_limit_error_is_exception(self):
        with pytest.raises(RateLimitError):
            raise RateLimitError("rate limited")


# ---------------------------------------------------------------------------
# PlaywrightFallback tests
# ---------------------------------------------------------------------------

class TestPlaywrightFallback:
    def test_disabled_by_default(self):
        pf = PlaywrightFallback(user_agent=UA, enabled=False)
        assert not pf.enabled

    def test_disabled_fetch_returns_zero(self):
        pf = PlaywrightFallback(user_agent=UA, enabled=False)
        code, content, headers, err = pf.fetch("https://example.com")
        assert code == 0
        assert content == b""
        assert "disabled" in err.lower()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_register_and_retrieve(self):
        from src.soccer_factory.sources.http_collector import HttpCollector as HC
        register_collector("test_source")(HC)
        cls = get_collector("test_source")
        assert cls is HC

    def test_get_missing_raises(self):
        with pytest.raises(ValueError, match="not found"):
            get_collector("definitely_not_registered_xyz")

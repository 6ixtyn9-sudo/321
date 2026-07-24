"""Unit tests for the grading / audit pipeline."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.soccer_factory.grading.audit_pipeline import (
    _match_outcome,
    aggregate,
    reconcile,
    _result_from_record,
)
from src.soccer_factory.schemas.predictions import Prediction
from src.soccer_factory.grading.grade import grade_prediction
from src.soccer_factory.schemas.results import Result


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _pred(mid, selection, prob, market="1x2"):
    return Prediction(
        prediction_id=f"p_{mid}_{selection}",
        match_id=mid,
        market=market,
        selection=selection,
        probability=prob,
        confidence_grade="B",
        model_version="test",
        feature_cutoff=NOW,
        created_at=NOW,
        reasons=[],
        data_quality="verified",
    )


class TestMatchOutcome:
    def test_home_win(self):
        assert _match_outcome(2, 1) == "1"

    def test_draw(self):
        assert _match_outcome(1, 1) == "X"

    def test_away_win(self):
        assert _match_outcome(0, 3) == "2"


class TestResultFromRecord:
    def test_builds_result(self):
        rec = {"home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1}
        r = _result_from_record(rec)
        assert r.status == "finished"
        assert r.home_score == 2
        assert r.away_score == 1
        assert r.match_outcome == "1"
        assert r.total_goals == 3
        assert r.btts_result is True
        assert r.over_25_result is True

    def test_btts_no(self):
        r = _result_from_record({"home_score": 2, "away_score": 0})
        assert r.btts_result is False
        assert r.over_25_result is False


class TestReconcile:
    def test_exact_match_grades_correctly(self):
        preds = [_pred("m1", "1", 0.6)]
        meta = {"p_m1_1": {"home_team": "Arsenal", "away_team": "Chelsea", "competition": "PL", "match_date": "2026-07-24", "source": "baseline"}}
        results = [{"home_team": "Arsenal", "away_team": "Chelsea", "home_score": 2, "away_score": 1, "competition": "PL"}]
        rows = reconcile(preds, meta, results)
        assert len(rows) == 1
        assert rows[0]["correct"] is True
        assert rows[0]["final_score"] == "2-1"
        assert rows[0]["brier"] == pytest.approx((0.6 - 1.0) ** 2)

    def test_fuzzy_match_grades(self):
        preds = [_pred("m1", "X", 0.3)]
        meta = {"p_m1_X": {"home_team": "Man Utd", "away_team": "Nottm Forest", "competition": "PL"}}
        results = [{"home_team": "Manchester United", "away_team": "Nottingham F.", "home_score": 1, "away_score": 1}]
        rows = reconcile(preds, meta, results)
        assert len(rows) == 1
        assert rows[0]["correct"] is True  # 1-1 is X
        assert rows[0]["status"] == "graded"

    def test_unmatched_result_marks_row(self):
        preds = [_pred("m1", "1", 0.7)]
        meta = {"p_m1_1": {"home_team": "NoSuch FC", "away_team": "Missing AFC"}}
        results = [{"home_team": "Arsenal", "away_team": "Chelsea", "home_score": 2, "away_score": 1}]
        rows = reconcile(preds, meta, results)
        assert rows[0]["status"] == "unmatched_result"
        assert rows[0]["correct"] is None


class TestAggregate:
    def test_overall_stats(self):
        rows = [
            {"correct": True, "probability": 0.7, "brier": (0.7-1)**2, "source": "baseline",
             "market": "1x2", "confidence_grade": "B", "competition": "PL", "status": "graded"},
            {"correct": False, "probability": 0.6, "brier": (0.6-0)**2, "source": "baseline",
             "market": "1x2", "confidence_grade": "B", "competition": "PL", "status": "graded"},
            {"correct": True, "probability": 0.8, "brier": (0.8-1)**2, "source": "forebet",
             "market": "btts", "confidence_grade": "A", "competition": "PL", "status": "graded"},
            {"status": "unmatched_result", "correct": None},
        ]
        summary = aggregate(rows)
        assert summary["overall"]["settled"] == 3
        assert summary["overall"]["wins"] == 2
        assert summary["overall"]["losses"] == 1
        assert summary["overall"]["hit_rate"] == pytest.approx(2/3, abs=0.001)
        assert summary["unmatched_results"] == 1
        assert "1x2" in summary["by_market"]
        assert summary["by_market"]["1x2"]["settled"] == 2
        assert summary["by_source"]["forebet"]["wins"] == 1

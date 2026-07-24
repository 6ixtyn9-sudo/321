"""End-to-end grading/calibration pipeline.

Given:
  * Frozen predictions under ``data/reports/report_<date>.json`` (produced by
    ``freeze``).
  * Settled result-detail pages collected by SoccerStats live runs (or any
    other source that emits :class:`Result` records into ``data/raw/**`` and
    match detail summary files from ``extract-results``).

Produces:
  * ``data/reports/grade_<date>.json`` — one graded prediction per row
    (includes brier score contribution, calibration bucket, source, market).
  * ``data/reports/audit_<datestr>.json`` — the user-audit-style summary
    (hit rate, ROI, calibration, per-market/source/league breakdowns).

The Edge-Factory audit you pasted is the target shape: we reproduce its
numbers automatically rather than by hand.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..identity.matcher import match_match, normalize_team_name
from ..schemas.predictions import Prediction, normalize_market
from ..schemas.results import Result, Grading
from .grade import grade_prediction


DATA_RAW = "data/raw"
DATA_REPORTS = "data/reports"


# ---------------------------------------------------------------------------
# Loading frozen predictions + settled results
# ---------------------------------------------------------------------------


def load_frozen_report(report_date: str) -> Dict[str, Any]:
    """Load a frozen report_<date>.json file from ``data/reports``."""
    path = Path(DATA_REPORTS) / f"report_{report_date}.json"
    if not path.exists():
        raise FileNotFoundError(f"No frozen report at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_result_summaries() -> List[Dict[str, Any]]:
    """Walk all ``soccerstats_result_details_*.json`` reports in ``data/reports``
    and flatten the result pages into a list of records with final scores.

    These reports are produced by the ``extract-results`` CLI command from
    saved result-detail pages.
    """
    out: List[Dict[str, Any]] = []
    for rp in Path(DATA_REPORTS).glob("soccerstats_result_details_*.json"):
        try:
            doc = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for page in doc.get("result_pages", []):
            summary = page.get("summary") or {}
            fs = summary.get("final_score")
            if not fs:
                continue
            home_score = fs.get("home") if isinstance(fs, dict) else None
            away_score = fs.get("away") if isinstance(fs, dict) else None
            if home_score is None or away_score is None:
                continue
            out.append({
                "match_id": page.get("match_id"),
                "home_team": page.get("home_team"),
                "away_team": page.get("away_team"),
                "competition": page.get("competition"),
                "home_score": home_score,
                "away_score": away_score,
                "total_goals": summary.get("total_goals"),
                "btts": summary.get("btts"),
                "source_report": str(rp.name),
            })
    return out


def load_results_from_raw() -> List[Dict[str, Any]]:
    """Walk soccerstats raw run directories and parse any ``matches.json`` /
    ``fixture_links.jsonl`` already annotated with scores (SoccerStats
    ``matches.asp`` for yesterday already contains final scores on the home
    page — see SoccerStatsParser's status handling).

    This is a lo-fi fallback used when no formal extract-results report
    exists; it pulls final scores directly off the parsed Match objects in
    interim if available.
    """
    out: List[Dict[str, Any]] = []
    interim_matches = Path("data/interim/matches.json")
    if interim_matches.exists():
        try:
            ms = json.loads(interim_matches.read_text(encoding="utf-8"))
            for m in ms:
                # SoccerStats live index yesterday includes FT scores in status text.
                # We don't currently parse those to Match fields (Match schema has
                # no home_score/away_score per earlier decision), so this is largely
                # a placeholder for when we add score-aware observation joining.
                if m.get("status") in ("finished", "full_time"):
                    out.append({
                        "match_id": m.get("match_id"),
                        "home_team": m.get("home_team"),
                        "away_team": m.get("away_team"),
                        "competition": m.get("competition"),
                    })
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Reconciliation: frozen prediction (home, away) -> settled result
# ---------------------------------------------------------------------------


def _match_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "1"
    if home_score < away_score:
        return "2"
    return "X"


def _result_from_record(rec: Dict[str, Any]) -> Result:
    hs = rec.get("home_score")
    aws = rec.get("away_score")
    tg = rec.get("total_goals")
    if tg is None and hs is not None and aws is not None:
        tg = hs + aws
    btts = rec.get("btts")
    if btts is None and hs is not None and aws is not None:
        btts = (hs > 0 and aws > 0)
    outcome = _match_outcome(hs, aws) if hs is not None and aws is not None else None
    return Result(
        match_id=rec.get("match_id") or "unknown",
        status="finished",
        home_score=hs,
        away_score=aws,
        match_outcome=outcome,
        total_goals=tg,
        btts_result=btts,
        over_25_result=(tg > 2) if tg is not None else None,
    )


def reconcile(
    predictions: List[Prediction],
    prediction_metadata: Dict[str, Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Match each prediction to a settled result using pair-level matching
    on home/away team names. Returns list of grade rows (one per prediction).
    """
    # Index results by (home_norm, away_norm) for exact lookup
    by_exact: Dict[Tuple[str, str], Dict[str, Any]] = {}
    all_results: List[Dict[str, Any]] = []
    for r in results:
        h, a = r.get("home_team", ""), r.get("away_team", "")
        if not h or not a:
            continue
        key = (normalize_team_name(h), normalize_team_name(a))
        by_exact[key] = r
        all_results.append(r)

    graded: List[Dict[str, Any]] = []
    for p in predictions:
        meta = prediction_metadata.get(p.prediction_id, {})
        home = meta.get("home_team")
        away = meta.get("away_team")
        competition = meta.get("competition")
        match_date = meta.get("match_date")
        source = meta.get("source", "321-baseline")

        # Try exact match first
        rec = None
        if home and away:
            rec = by_exact.get((normalize_team_name(home), normalize_team_name(away)))
            # Fuzzy fallback
            if rec is None:
                best = None
                best_sim = 0.0
                for r in all_results:
                    rh, ra = r.get("home_team", ""), r.get("away_team", "")
                    ok, sim, reason = match_match(home, away, rh, ra)
                    if ok and sim > best_sim:
                        best_sim = sim
                        best = r
                if best is not None:
                    rec = best

        if rec is None:
            graded.append({
                "prediction_id": p.prediction_id,
                "match_id": p.match_id,
                "source": source,
                "market": p.market,
                "selection": p.selection,
                "probability": p.probability,
                "confidence_grade": p.confidence_grade,
                "home_team": home,
                "away_team": away,
                "competition": competition,
                "match_date": match_date,
                "status": "unmatched_result",
                "correct": None,
                "brier": None,
            })
            continue

        result_obj = _result_from_record(rec)
        g = grade_prediction(p, result_obj, grading_source="soccerstats_result_summary")
        actual_p = {
            "1": (1.0 if result_obj.match_outcome == "1" else 0.0),
            "X": (1.0 if result_obj.match_outcome == "X" else 0.0),
            "2": (1.0 if result_obj.match_outcome == "2" else 0.0),
            "Over 2.5": (1.0 if result_obj.over_25_result else 0.0) if result_obj.over_25_result is not None else None,
            "Under 2.5": (0.0 if result_obj.over_25_result else 1.0) if result_obj.over_25_result is not None else None,
            "Yes": (1.0 if result_obj.btts_result else 0.0) if result_obj.btts_result is not None else None,
            "No": (0.0 if result_obj.btts_result else 1.0) if result_obj.btts_result is not None else None,
            "1X": (1.0 if result_obj.match_outcome in ("1", "X") else 0.0) if result_obj.match_outcome else None,
            "X2": (1.0 if result_obj.match_outcome in ("X", "2") else 0.0) if result_obj.match_outcome else None,
            "12": (1.0 if result_obj.match_outcome in ("1", "2") else 0.0) if result_obj.match_outcome else None,
        }.get(p.selection)
        brier = ((p.probability - actual_p) ** 2) if actual_p is not None else None
        graded.append({
            "prediction_id": p.prediction_id,
            "match_id": p.match_id,
            "source": source,
            "market": p.market,
            "selection": p.selection,
            "probability": p.probability,
            "confidence_grade": p.confidence_grade,
            "home_team": rec.get("home_team", home),
            "away_team": rec.get("away_team", away),
            "competition": rec.get("competition", competition),
            "match_date": match_date,
            "final_score": g.final_score,
            "actual_outcome": g.actual_outcome,
            "correct": g.correct,
            "brier": brier,
            "status": "graded" if g.correct is not None else (g.unresolved_status or "unknown"),
        })
    return graded


# ---------------------------------------------------------------------------
# Aggregation: produce the Edge-Factory-style audit summary
# ---------------------------------------------------------------------------


def _bucket(p: float) -> str:
    """Probability bucket for calibration curves."""
    if p < 0.5:
        return "<50%"
    if p < 0.6:
        return "50-60%"
    if p < 0.7:
        return "60-70%"
    if p < 0.8:
        return "70-80%"
    if p < 0.9:
        return "80-90%"
    return "90%+"


@dataclass
class _Agg:
    n: int = 0
    wins: int = 0
    losses: int = 0
    unresolved: int = 0
    brier_sum: float = 0.0
    brier_n: int = 0
    prob_sum: float = 0.0

    def add(self, correct: Optional[bool], prob: Optional[float], brier: Optional[float]):
        self.n += 1
        if correct is True:
            self.wins += 1
        elif correct is False:
            self.losses += 1
        else:
            self.unresolved += 1
        if brier is not None:
            self.brier_sum += brier
            self.brier_n += 1
        if prob is not None:
            self.prob_sum += prob

    def hit_rate(self) -> Optional[float]:
        settled = self.wins + self.losses
        return self.wins / settled if settled else None

    def avg_prob(self) -> Optional[float]:
        settled = self.wins + self.losses
        return self.prob_sum / settled if settled else None

    def brier(self) -> Optional[float]:
        return self.brier_sum / self.brier_n if self.brier_n else None

    def as_dict(self) -> Dict[str, Any]:
        settled = self.wins + self.losses
        d = {
            "settled": settled,
            "wins": self.wins,
            "losses": self.losses,
            "unresolved": self.unresolved,
        }
        hr = self.hit_rate()
        if hr is not None:
            d["hit_rate"] = round(hr, 4)
        ap = self.avg_prob()
        if ap is not None:
            d["avg_predicted_prob"] = round(ap, 4)
            if hr is not None:
                d["calibration_error"] = round(ap - hr, 4)
        br = self.brier()
        if br is not None:
            d["brier"] = round(br, 4)
        return d


def aggregate(graded_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    overall = _Agg()
    by_market: Dict[str, _Agg] = defaultdict(_Agg)
    by_source: Dict[str, _Agg] = defaultdict(_Agg)
    by_market_source: Dict[str, _Agg] = defaultdict(_Agg)
    by_confidence: Dict[str, _Agg] = defaultdict(_Agg)
    by_prob_bucket: Dict[str, _Agg] = defaultdict(_Agg)
    by_competition: Dict[str, _Agg] = defaultdict(_Agg)
    unmatched = 0

    for r in graded_rows:
        if r["status"] == "unmatched_result":
            unmatched += 1
            continue
        if r.get("correct") is None and r["status"] != "graded":
            # unresolved (postponed etc) — still count
            pass
        bucket_keys = [
            ("overall", overall),
            (f"market:{r['market']}", by_market[r["market"]]),
            (f"source:{r['source']}", by_source[r["source"]]),
            (f"market_source:{r['market']}|{r['source']}", by_market_source[f"{r['market']}|{r['source']}"]),
            (f"grade:{r['confidence_grade']}", by_confidence[r["confidence_grade"]]),
        ]
        if r.get("probability") is not None:
            bucket_keys.append((f"prob:{_bucket(r['probability'])}", by_prob_bucket[_bucket(r["probability"])]))
        if r.get("competition"):
            bucket_keys.append((f"comp:{r['competition']}", by_competition[r["competition"]]))
        for _, agg in bucket_keys:
            agg.add(r.get("correct"), r.get("probability"), r.get("brier"))

    def _flatten(d: Dict[str, _Agg]) -> Dict[str, Dict[str, Any]]:
        # Strip the "type:" prefix used internally for namespacing (e.g.
        # "market:1x2" -> "1x2", "comp:Premier League" -> "Premier League").
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in sorted(d.items()):
            clean = k.split(":", 1)[1] if ":" in k else k
            out[clean] = v.as_dict()
        return out

    return {
        "overall": overall.as_dict(),
        "by_market": _flatten(by_market),
        "by_source": _flatten(by_source),
        "by_market_source": _flatten(by_market_source),
        "by_confidence_grade": _flatten(by_confidence),
        "by_probability_bucket": _flatten(by_prob_bucket),
        "by_competition": _flatten(by_competition),
        "unmatched_results": unmatched,
        "total_graded_rows": len(graded_rows),
    }


# ---------------------------------------------------------------------------
# Top-level entry point used by CLI.do_grade
# ---------------------------------------------------------------------------


def run_audit(report_date: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Path]:
    """Run the full audit: load frozen predictions, reconcile to results,
    aggregate, write ``grade_<date>.json`` and ``audit_<date>.json`` under
    ``data/reports``.
    """
    if report_date is None:
        # Default: most recent report_*.json
        candidates = sorted(Path(DATA_REPORTS).glob("report_*.json"))
        if not candidates:
            raise SystemExit("No frozen reports found in data/reports. Run `freeze` first.")
        report_date = candidates[-1].stem.replace("report_", "")

    frozen = load_frozen_report(report_date)
    predictions = []
    metadata: Dict[str, Dict[str, Any]] = {}
    # Frozen report shape: {"predictions": [...], "no_predictions": [...], "summary": {...}}
    for p in frozen.get("predictions", []):
        try:
            pred = Prediction.model_validate(p)
        except Exception:
            continue
        predictions.append(pred)
        # Best-effort: join.json records aren't embedded here; we'll recover
        # home/away from the joined output if available.
        metadata[pred.prediction_id] = {}

    # Recover match metadata (home/away/competition/date) from joined.json
    joined_path = Path("data/processed/joined.json")
    if joined_path.exists():
        try:
            joined = json.loads(joined_path.read_text(encoding="utf-8"))
            by_match_id: Dict[str, Dict[str, Any]] = {}
            for row in joined:
                m = row.get("match") or {}
                by_match_id[m.get("match_id")] = {
                    "home_team": m.get("home_team"),
                    "away_team": m.get("away_team"),
                    "competition": m.get("competition"),
                    "match_date": (m.get("scheduled_kickoff") or "")[:10],
                    "source": next(iter(m.get("source_urls", {}).keys()), None) or "321",
                }
            for pred in predictions:
                if pred.match_id in by_match_id:
                    metadata[pred.prediction_id] = dict(by_match_id[pred.match_id])
        except Exception:
            pass

    results = load_result_summaries()
    if not results:
        results = load_results_from_raw()

    graded = reconcile(predictions, metadata, results)
    summary = aggregate(graded)
    summary["report_date"] = report_date
    summary["graded_at"] = datetime.now(timezone.utc).isoformat()
    summary["results_available"] = len(results)

    grade_path = Path(DATA_REPORTS) / f"grade_{report_date}.json"
    audit_path = Path(DATA_REPORTS) / f"audit_{report_date}.json"
    grade_path.write_text(json.dumps({
        "report_date": report_date,
        "graded_at": summary["graded_at"],
        "rows": graded,
    }, indent=2, default=str), encoding="utf-8")
    audit_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return graded, summary, audit_path

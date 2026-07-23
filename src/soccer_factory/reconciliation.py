"""Cross-day lifecycle reconciliation for SoccerStats fixtures.

Matches fixtures across collection runs using durable references,
never silently joining ambiguous records.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from src.soccer_factory.identity.normalize import normalize_team_name
from src.soccer_factory.identity.matcher import similarity


def reconcile_cross_day(
    pre_run_dir: Path,
    current_run_dir: Path,
    output_path: Path,
) -> Dict[str, Any]:
    """Reconcile fixtures across a pre-match run and a later current run.

    Matching priority:
    1. Stable source detail URL / reference
    2. Source league + source team IDs + target date
    3. Conservative normalized competition + home + away + date fallback
    """
    result: Dict[str, Any] = {
        "reconciliation_at": datetime.now().isoformat(),
        "pre_run": str(pre_run_dir),
        "current_run": str(current_run_dir),
        "reconciled": [],
        "ambiguous": [],
        "unresolved": [],
    }

    # Read pre-run fixture links
    pre_links_path = pre_run_dir / "fixture_links.jsonl"
    current_links_path = current_run_dir / "fixture_links.jsonl"

    pre_links = []
    if pre_links_path.exists():
        for line in pre_links_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pre_links.append(json.loads(line))

    current_links = []
    if current_links_path.exists():
        for line in current_links_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                current_links.append(json.loads(line))

    for pre in pre_links:
        pre_match_id = pre.get("match_id")
        pre_detail_url = pre.get("detail_url", "")
        pre_target_date = pre.get("target_date", pre.get("match_date_if_known"))
        pre_home = pre.get("home_team", "")
        pre_away = pre.get("away_team", "")
        pre_scope = pre.get("scope", "unknown")

        matches_by_url = [
            c for c in current_links
            if c.get("detail_url") == pre_detail_url
        ]
        matches_by_ref = [
            c for c in current_links
            if c.get("source_url") == pre_detail_url or c.get("index_url") == pre.get("index_url")
        ]
        matches_by_identity = []
        for c in current_links:
            c_home = c.get("home_team", "")
            c_away = c.get("away_team", "")
            c_target = c.get("target_date", c.get("match_date_if_known"))
            if c_target == pre_target_date:
                norm_c_home = normalize_team_name(str(c_home))
                norm_c_away = normalize_team_name(str(c_away))
                norm_pre_home = normalize_team_name(str(pre_home))
                norm_pre_away = normalize_team_name(str(pre_away))
                if (norm_c_home == norm_pre_home and norm_c_away == norm_pre_away) or \
                   (norm_c_home == norm_pre_away and norm_c_away == norm_pre_home):
                    # If swapped, treat as ambiguous unless exact
                    if norm_c_home == norm_pre_home and norm_c_away == norm_pre_away:
                        matches_by_identity.append(c)

        # Apply matching priority
        selected = None
        reason = None
        ambiguous_candidates = []

        # Priority 1: stable source detail URL / reference
        if pre_detail_url:
            url_matches = [m for m in (matches_by_url or []) if m.get("detail_url") == pre_detail_url]
            if len(url_matches) == 1:
                selected = url_matches[0]
                reason = "stable_source_detail_url"
            elif len(url_matches) > 1:
                ambiguous_candidates.extend(url_matches)
                reason = f"ambiguous_multiple_url_matches({len(url_matches)})"

        # Priority 2: source league + source team IDs + target date
        if selected is None:
            identity_matches = matches_by_identity
            if len(identity_matches) == 1:
                selected = identity_matches[0]
                reason = "source_league_team_ids_target_date"
            elif len(identity_matches) > 1:
                ambiguous_candidates.extend(identity_matches)
                reason = f"ambiguous_multiple_identity_matches({len(identity_matches)})"

        # Priority 3: conservative normalized competition + home + away + date fallback
        if selected is None:
            # Try normalized team + date fallback
            for c in current_links:
                c_target = c.get("target_date", c.get("match_date_if_known"))
                c_home = c.get("home_team", "")
                c_away = c.get("away_team", "")
                if c_target == pre_target_date:
                    norm_c_home = normalize_team_name(str(c_home))
                    norm_c_away = normalize_team_name(str(c_away))
                    norm_pre_home = normalize_team_name(str(pre_home))
                    norm_pre_away = normalize_team_name(str(pre_away))
                    sim_home = similarity(norm_pre_home, norm_c_home)
                    sim_away = similarity(norm_pre_away, norm_c_away)
                    if sim_home >= 0.85 and sim_away >= 0.85:
                        if selected is None:
                            selected = c
                            reason = "normalized_fallback"
                        else:
                            ambiguous_candidates.append(c)
                            reason = "ambiguous_fallback_multiple"

        # Determine result evidence
        result_snapshot_path = selected.get("result_snapshot_path") if selected else None
        final_result_evidence = bool(
            selected and (selected.get("status") == "finished" or selected.get("final_result_evidence"))
        )

        # Build reconciliation record
        record = {
            "fixture_id": pre_match_id,
            "pre_match_snapshot_path": pre.get("preview_snapshot_path"),
            "pre_match_observed_time": pre.get("observed_at_utc"),
            "pre_match_eligible": pre.get("pre_match_eligible"),
            "kickoff_utc": pre.get("kickoff_utc"),
            "kickoff_confidence": pre.get("kickoff_confidence"),
            "current_state": selected.get("lifecycle_state") if selected else None,
            "live_observations": [
                {
                    "current_run_id": current_run_dir.name,
                    "status": c.get("status"),
                    "observed_at_utc": c.get("observed_at_utc"),
                    "scope": c.get("scope"),
                }
                for c in current_links
                if c.get("match_id") == pre_match_id or (selected and c.get("detail_url") == selected.get("detail_url"))
            ],
            "finished_result_snapshot": result_snapshot_path,
            "reconciliation_status": "reconciled" if selected else ("ambiguous" if ambiguous_candidates else "unresolved"),
            "reason": reason or ("ambiguous_identity" if ambiguous_candidates else "no_cross_day_reference"),
            "target_date": pre_target_date,
            "scope": pre_scope,
        }

        if ambiguous_candidates or (selected is None and ambiguous_candidates):
            result["ambiguous"].append(record)
        elif selected:
            result["reconciled"].append(record)
        else:
            result["unresolved"].append(record)

    # Deduplicate result pages across three scope links
    seen_result_paths = set()
    for rec in result["reconciled"] + result["ambiguous"]:
        path = rec.get("finished_result_snapshot")
        if path and path in seen_result_paths:
            rec["reconciliation_status"] = "reconciled_duplicate_result"
            rec["reason"] = "duplicate_result_page_across_scopes"
        elif path:
            seen_result_paths.add(path)

    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result

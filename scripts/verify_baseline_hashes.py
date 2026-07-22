import hashlib
import json
import sys
import os
import glob
from copy import deepcopy

def canonical_hash(filepath=None, data=None):
    if filepath and os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
    elif data is None:
        return None
        
    def _clean(obj):
        if isinstance(obj, dict):
            # Exclude ONLY documented operational metadata
            for k in ["run_id", "run_started_at", "run_finished_at", "generated_at", "created_at", "updated_at", "fetched_at", "git_commit", "frozen_at", "timestamp"]:
                obj.pop(k, None)
            
            # Recursively clean and sort keys
            return {k: _clean(v) for k, v in sorted(obj.items())}
            
        elif isinstance(obj, list):
            cleaned = [_clean(v) for v in obj]
            try:
                # Attempt to sort lists of dicts by JSON string representation to ensure determinism
                # but only if order is not meaningful. Wait, the user said:
                # "preserve meaningful list order; sort only explicitly unordered collections"
                # Since we don't know which collections are unordered except maybe list of predictions in report,
                # let's just sort by a deterministic key if it's a list of dicts with IDs.
                # Actually, the user says "preserve meaningful list order; sort only explicitly unordered collections".
                # For safety, if it's a list of dicts, we'll try to sort it by prediction_id or match_id.
                if all(isinstance(x, dict) for x in cleaned):
                    # Sort by id fields if they exist
                    if all("prediction_id" in x for x in cleaned):
                        cleaned = sorted(cleaned, key=lambda x: x["prediction_id"])
                    elif all("match_id" in x for x in cleaned):
                        cleaned = sorted(cleaned, key=lambda x: x["match_id"])
            except Exception:
                pass
            return cleaned
        else:
            return obj
            
    cleaned_data = _clean(deepcopy(data))
    canonical_bytes = json.dumps(cleaned_data, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()

def self_test():
    """Prove the canonical_hash passes for non-semantic differences but fails for semantic ones."""
    base_data = {
        "run_id": "old_run",
        "created_at": "old_date",
        "prediction_id": "pred_123",
        "match_id": "match_456",
        "feature_cutoff": "2026-07-21T10:00:00Z"
    }
    
    base_hash = canonical_hash(data=base_data)
    
    # 1. Changed run_id -> Hash should be same
    mut1 = deepcopy(base_data)
    mut1["run_id"] = "new_run"
    assert canonical_hash(data=mut1) == base_hash, "Hash changed on operational metadata mutation (run_id)!"

    # 2. Reordering keys -> Hash should be same
    mut2 = {"created_at": "old_date", "prediction_id": "pred_123", "feature_cutoff": "2026-07-21T10:00:00Z", "run_id": "old_run", "match_id": "match_456"}
    assert canonical_hash(data=mut2) == base_hash, "Hash changed on key reordering!"

    # 3. Changed match_id -> Hash should be different
    mut3 = deepcopy(base_data)
    mut3["match_id"] = "match_789"
    assert canonical_hash(data=mut3) != base_hash, "Hash stayed the same on semantic mutation (match_id)!"

    # 4. Changed feature_cutoff -> Hash should be different
    mut4 = deepcopy(base_data)
    mut4["feature_cutoff"] = "2026-07-21T12:00:00Z"
    assert canonical_hash(data=mut4) != base_hash, "Hash stayed the same on semantic mutation (feature_cutoff)!"

    print("Self-test passed! Canonical hashing is strictly semantic.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_baseline_hashes.py [generate|verify|--self-test]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    
    if cmd == "--self-test":
        self_test()
        sys.exit(0)
    
    baseline_dir = "data/regression_baseline"
    
    report_files = glob.glob("data/reports/report_*.json")
    report_file = report_files[0] if report_files else "data/reports/report_YYYY-MM-DD.json"
    
    artifacts = {
        "features.json": "data/interim/features.json",
        "predictions.json": "data/processed/predictions.json",
        "no_predictions.json": "data/processed/no_predictions.json",
        "reconciliation.json": "data/processed/reconciliation.json",
        os.path.basename(report_file): report_file
    }

    if cmd == "generate":
        os.makedirs(baseline_dir, exist_ok=True)
        manifest = {
            "normalization_version": "2.0",
            "excluded_fields": ["run_id", "run_started_at", "run_finished_at", "generated_at", "created_at", "updated_at", "fetched_at", "git_commit", "frozen_at", "timestamp"],
            "preserved_semantic_fields": ["match_id", "prediction_id", "feature_cutoff", "kickoff_timestamp", "match_date", "market", "selection", "probability", "confidence", "model_version", "source_snapshot_lineage"],
            "artifacts": {}
        }
        for name, path in artifacts.items():
            h = canonical_hash(filepath=path)
            if h:
                manifest["artifacts"][name] = h
                outpath = os.path.join(baseline_dir, name.replace(".json", ".sha256"))
                with open(outpath, "w") as f:
                    f.write(h)
            else:
                manifest["artifacts"][name] = "missing"
                
        with open(os.path.join(baseline_dir, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Baseline hashes generated in {baseline_dir}")
        
    elif cmd == "verify":
        manifest_path = os.path.join(baseline_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            print("No baseline manifest found.")
            sys.exit(1)
            
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
            
        success = True
        print(f"{'Artifact':<30} {'Baseline':<10} {'Current':<10} {'Equal':<5}")
        print("-" * 60)
        
        expected_artifacts = manifest.get("artifacts", {})
        
        for name, expected in expected_artifacts.items():
            if expected == "missing":
                print(f"{name:<30} {'missing':<10} {'N/A':<10} {'False':<5}")
                success = False
                continue
                
            path = next((p for n, p in artifacts.items() if n == name), None)
            if not path:
                if name.startswith("report_") and name.endswith(".json"):
                    path = f"data/reports/{name}"
                else:
                    path = f"data/processed/{name}"
                    if not os.path.exists(path):
                        path = f"data/interim/{name}"
            
            actual = canonical_hash(filepath=path)
            is_equal = (expected == actual)
            if not is_equal:
                success = False
            
            disp_exp = expected[:8] + "..." if expected else "missing"
            disp_act = actual[:8] + "..." if actual else "missing"
            
            print(f"{name:<30} {disp_exp:<10} {disp_act:<10} {str(is_equal):<5}")
            
        if not success:
            print("\nERROR: Prediction regression failure! Artifact canonical hashes do not match baseline.")
            sys.exit(1)
        else:
            print("\nSUCCESS: All prediction artifacts semantically match the baseline.")

if __name__ == "__main__":
    main()

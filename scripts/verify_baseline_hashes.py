import hashlib
import json
import sys
import os
import glob

def canonical_hash(filepath):
    if not os.path.exists(filepath):
        return None
        
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    def _clean(obj):
        if isinstance(obj, dict):
            # Remove unstable keys
            for k in ["run_id", "created_at", "updated_at", "generated_at", "fetched_at", "git_commit"]:
                obj.pop(k, None)
            
            # Recursively clean and sort keys
            return {k: _clean(v) for k, v in sorted(obj.items())}
            
        elif isinstance(obj, list):
            # Sort lists of dicts if they have deterministic IDs, otherwise preserve order (for lists where order is meaningful)
            cleaned = [_clean(v) for v in obj]
            try:
                # Attempt to sort the list of dictionaries by common ID fields or JSON string representation
                cleaned = sorted(cleaned, key=lambda x: json.dumps(x, sort_keys=True))
            except Exception:
                pass
            return cleaned
        else:
            return obj
            
    cleaned_data = _clean(data)
    canonical_bytes = json.dumps(cleaned_data, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_baseline_hashes.py [generate|verify]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    
    baseline_dir = "data/regression_baseline"
    
    # Need to discover the report file
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
            "normalization_version": "1.0",
            "excluded_fields": ["run_id", "created_at", "updated_at", "generated_at", "fetched_at", "git_commit"],
            "artifacts": {}
        }
        for name, path in artifacts.items():
            h = canonical_hash(path)
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
                
            # For verification, we map back the basename to the path
            # But the report file name might have changed dates. 
            # We should just look for it in the current artifacts list or check if it exists.
            path = next((p for n, p in artifacts.items() if n == name), None)
            if not path:
                # Try to see if it's a report file
                if name.startswith("report_") and name.endswith(".json"):
                    path = f"data/reports/{name}"
                else:
                    path = f"data/processed/{name}"
                    if not os.path.exists(path):
                        path = f"data/interim/{name}"
            
            actual = canonical_hash(path)
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

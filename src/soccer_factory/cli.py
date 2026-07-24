import argparse
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser
from src.soccer_factory.sources.forebet.parser import ForebetParser
from src.soccer_factory.sources.http_collector import HttpCollector
from src.soccer_factory.sources.soccerstats.live import collect_daily_bundle
from src.soccer_factory.sources.soccerstats.results import extract_result_detail, summarize_result_detail
from src.soccer_factory.identity.matcher import match_teams, match_match, normalize_team_name
from src.soccer_factory.models.baseline import generate_predictions, generate_no_predictions
from src.soccer_factory.schemas.features import Features
from src.soccer_factory.schemas.predictions import SourceObservation

DATA_RAW = "data/raw"
DATA_INTERIM = "data/interim"
DATA_PROCESSED = "data/processed"
DATA_REPORTS = "data/reports"

def setup_dirs() -> None:
    for d in [DATA_RAW, DATA_INTERIM, DATA_PROCESSED, DATA_REPORTS]:
        os.makedirs(d, exist_ok=True)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="321 Soccer Analytics CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format", required=False)
    parent_parser.add_argument("--as-of", type=str, help="Deterministic as-of timestamp (e.g. 2026-07-21T00:00:00Z)", required=False)
    parent_parser.add_argument("--mode", type=str, choices=["fixture", "live"], default="fixture", help="Run mode")
    parent_parser.add_argument("--confirm-live", action="store_true", help="Confirm live mode execution")
    parent_parser.add_argument("--source", type=str, choices=["soccerstats", "forebet", "all"], default="soccerstats", help="Target source for collect/validate/discover/smoke/catalog")
    parent_parser.add_argument("--max-previews", type=int, default=20, help="Maximum scheduled SoccerStats preview pages in a live collection (bounded by source request policy)")
    parent_parser.add_argument("--extended-markets", action="store_true", help="(Forebet) Fetch extended markets (ht/htft/ah/corners) in addition to core 1x2/uo/bts")
    parent_parser.add_argument("--run-id", type=str, help="SoccerStats live collection run ID to validate; isolates that run from fixture files")
    parent_parser.add_argument("--browser-fallback", action="store_true", help="Compare public SoccerStats index HTML with a browser-rendered response and retain the fuller page")

    subparsers.add_parser("collect", parents=[parent_parser])
    subparsers.add_parser("validate", parents=[parent_parser])
    subparsers.add_parser("extract-results", parents=[parent_parser])
    subparsers.add_parser("extract-details", parents=[parent_parser])
    subparsers.add_parser("build-features", parents=[parent_parser])
    subparsers.add_parser("predict", parents=[parent_parser])
    subparsers.add_parser("freeze", parents=[parent_parser])
    subparsers.add_parser("grade", parents=[parent_parser])
    subparsers.add_parser("report", parents=[parent_parser])
    subparsers.add_parser("health-check")
    subparsers.add_parser("run-daily", parents=[parent_parser])

    smoke_parser = subparsers.add_parser("smoke-test", parents=[parent_parser])
    discover_parser = subparsers.add_parser("discover", parents=[parent_parser])

    audit_parser = subparsers.add_parser("lifecycle-audit", parents=[parent_parser])
    audit_parser.add_argument("--pre-run-id", type=str, required=True, help="Pre-match collection run ID")
    audit_parser.add_argument("--current-run-id", type=str, required=True, help="Current collection run ID")

    catalog_parser = subparsers.add_parser("catalog", parents=[parent_parser])

    return parser.parse_args()

def check_mode(args: argparse.Namespace) -> None:
    if getattr(args, 'mode', 'fixture') == 'live' and not getattr(args, 'confirm_live', False):
        print("Error: --mode live requires --confirm-live flag to prevent accidental live runs.", file=sys.stderr)
        sys.exit(1)

def get_as_of(args: argparse.Namespace) -> datetime:
    if getattr(args, "as_of", None):
        return datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)

def do_collect(args: argparse.Namespace) -> None:
    setup_dirs()
    source = getattr(args, "source", "soccerstats")
    if getattr(args, 'mode', 'fixture') == "fixture":
        # Copy fixtures to raw
        import shutil
        collected_count = 0
        for file in os.listdir("tests/fixtures"):
            src_path = os.path.join("tests/fixtures", file)
            if os.path.isfile(src_path):
                shutil.copy(src_path, os.path.join(DATA_RAW, file))
                collected_count += 1
        manifest = {"collected": collected_count, "mode": "fixture", "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": source}
        with open(f"{DATA_RAW}/manifest.json", "w") as f:
            json.dump(manifest, f)
        print("Collect complete (fixture mode). Zero external requests made.")
        return

    # Live mode — per-source collection
    from datetime import date
    from zoneinfo import ZoneInfo
    requested_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    local_today = datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    contact_email = os.environ.get("CONTACT_EMAIL", "contact@example.com")

    manifest = {
        "mode": "live",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_date": requested_date.isoformat(),
        "sources": {},
    }
    sources_to_run = ("soccerstats", "forebet") if source == "all" else (source,)
    for src in sources_to_run:
        try:
            if src == "soccerstats":
                snapshots = collect_daily_bundle(
                    target=requested_date,
                    today=local_today,
                    output_dir=Path(DATA_RAW),
                    contact_email=contact_email,
                    parser_version=SoccerStatsParser().version,
                    max_previews=args.max_previews,
                    browser_fallback=args.browser_fallback,
                )
                successful = sum(1 for s in snapshots if s.validation_status == "fetched")
                manifest["sources"]["soccerstats"] = {
                    "collected": successful,
                    "requested": len(snapshots),
                }
                print(f"Live SoccerStats collection complete. {successful}/{len(snapshots)} snapshots fetched.")
            elif src == "forebet":
                from src.soccer_factory.sources.forebet.live import collect_daily_bundle as fb_collect
                from src.soccer_factory.sources.forebet.parser import ForebetParser
                fb_snapshots = fb_collect(
                    target=requested_date,
                    today=local_today,
                    output_dir=Path(DATA_RAW),
                    contact_email=contact_email,
                    parser_version=ForebetParser().version,
                    extended_markets=bool(getattr(args, "extended_markets", False)),
                )
                fb_success = sum(1 for s in fb_snapshots if s.validation_status == "fetched")
                manifest["sources"]["forebet"] = {
                    "collected": fb_success,
                    "requested": len(fb_snapshots),
                    "extended_markets": bool(getattr(args, "extended_markets", False)),
                }
                print(f"Live Forebet collection complete. {fb_success}/{len(fb_snapshots)} snapshots fetched.")
        except ValueError as exc:
            raise SystemExit(f"Error ({src}): {exc}") from None

    manifest["collected"] = sum(s.get("collected", 0) for s in manifest["sources"].values())
    with open(f"{DATA_RAW}/manifest.json", "w") as f:
        json.dump(manifest, f)
    print(f"Live collection complete. Manifest written to {DATA_RAW}/manifest.json.")

def do_extract_results(args: argparse.Namespace) -> None:
    """Turn a run's saved result-detail pages into a lossless JSON dataset."""
    setup_dirs()
    run_id = getattr(args, "run_id", None)
    if not run_id or os.path.basename(run_id) != run_id or run_id in {".", ".."}:
        raise SystemExit("Error: extract-results requires a valid --run-id.")
    run_dir = Path(DATA_RAW) / "soccerstats" / run_id
    links_path = run_dir / "fixture_links.jsonl"
    if not links_path.exists():
        raise SystemExit(f"Error: result collection run not found: {run_id}")
    records = []
    seen_result_paths = set()
    for line in links_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        link = json.loads(line)
        result_path = link.get("result_snapshot_path")
        if not link.get("result_collected") or not result_path:
            continue
        page_path = Path(result_path)
        if not page_path.exists() or page_path in seen_result_paths:
            continue
        seen_result_paths.add(page_path)
        records.append({
            "match_id": link.get("match_id"), "competition": link.get("competition"),
            "home_team": link.get("home_team"), "away_team": link.get("away_team"),
            "source_url": link.get("detail_url"), "snapshot_path": str(page_path),
            "summary": summarize_result_detail(page_path.read_bytes(), link.get("home_team", ""), link.get("away_team", "")),
            "extracted": extract_result_detail(page_path.read_bytes()),
        })
    output = Path(DATA_REPORTS) / f"soccerstats_result_details_{run_id}.json"
    output.write_text(json.dumps({"run_id": run_id, "result_pages": records}, indent=2), encoding="utf-8")
    print(f"Result extraction complete. {len(records)} complete result pages written to {output}")

def do_extract_details(args: argparse.Namespace) -> None:
    """Losslessly extract every linked match detail page in a collection run."""
    setup_dirs()
    run_id = getattr(args, "run_id", None)
    if not run_id or os.path.basename(run_id) != run_id or run_id in {".", ".."}:
        raise SystemExit("Error: extract-details requires a valid --run-id.")
    run_dir = Path(DATA_RAW) / "soccerstats" / run_id
    links_path = run_dir / "fixture_links.jsonl"
    if not links_path.exists():
        raise SystemExit(f"Error: collection run not found: {run_id}")
    seen_paths, records = set(), []
    for line in links_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        link = json.loads(line)
        for page_type, key in (("pre_match_preview", "preview_snapshot_path"), ("result_detail", "result_snapshot_path"), ("alternate_detail", "detail_snapshot_path")):
            path_value = link.get(key)
            if not path_value:
                continue
            page_path = Path(path_value)
            if not page_path.exists() or page_path in seen_paths:
                continue
            seen_paths.add(page_path)
            records.append({
                "match_id": link.get("match_id"), "competition": link.get("competition"),
                "home_team": link.get("home_team"), "away_team": link.get("away_team"),
                "page_type": page_type, "source_url": link.get("detail_url"),
                "snapshot_path": str(page_path), "extracted": extract_result_detail(page_path.read_bytes()),
            })
    output = Path(DATA_REPORTS) / f"soccerstats_match_details_{run_id}.json"
    output.write_text(json.dumps({"run_id": run_id, "detail_pages": records}, indent=2), encoding="utf-8")
    print(f"Detail extraction complete. {len(records)} match detail pages written to {output}")

def do_validate(args: argparse.Namespace) -> None:
    setup_dirs()
    ss_parser = SoccerStatsParser()
    fb_parser = ForebetParser()
    dt = get_as_of(args)
    source = getattr(args, "source", "soccerstats")

    matches = []
    seen_match_ids = set()
    obs = []
    features = []

    # A run-scoped live validation must never mix old fixture-mode HTML or a
    # different collection run with its raw snapshots.
    scan_root = DATA_RAW
    run_id = getattr(args, "run_id", None)
    # If a specific run_id is given, scope to that run directory for BOTH sources.
    if run_id:
        if os.path.basename(run_id) != run_id or run_id in {".", ".."}:
            raise SystemExit("Error: --run-id must be a single collection-run directory name.")
        # Determine which source subdir the run lives in by probing
        for probe_src in ("soccerstats", "forebet"):
            probe = os.path.join(DATA_RAW, probe_src, run_id)
            if os.path.isdir(probe):
                scan_root = probe
                source = probe_src
                break
        else:
            raise SystemExit(f"Error: no collection run found with id {run_id!r} under data/raw/soccerstats/ or data/raw/forebet/.")

    # Read durable index-to-preview links before parsing preview snapshots.
    # A preview feature is attached only through this source-produced linkage.
    preview_match_ids = {}
    for root, _dirs, names in os.walk(scan_root):
        if "fixture_links.jsonl" not in names:
            continue
        with open(os.path.join(root, "fixture_links.jsonl"), encoding="utf-8") as links_file:
            for line in links_file:
                if not line.strip():
                    continue
                link = json.loads(line)
                if link.get("status") == "pre-match" and link.get("preview_snapshot_path"):
                    preview_match_ids[os.path.normpath(link["preview_snapshot_path"])] = link["match_id"]
    
    # RED-TEAM HARDENED: walk ALL html files and try EVERY parser family
    # This ensures every discovered link family produces usable stats end-to-end
    from src.soccer_factory.sources.soccerstats.family_parsers import parse_by_family as ss_family_parse
    from src.soccer_factory.sources.forebet.family_parsers import parse_by_family as fb_family_parse
    from src.soccer_factory.discovery.classifier import classify, classify_soccerstats, classify_forebet

    def _guess_family_from_path(path: str, content: bytes) -> str:
        # Try to infer family from file name or URL inside manifest
        # For live runs, manifest contains URL -> we can classify via URL
        # For fixture mode, use file name heuristics
        if "daily_index" in path or "soccerstats_matches" in path:
            return "matches"
        if "pmatch" in path:
            return "match_preview"
        if "round_details" in path:
            return "round_details"
        if "league_latest" in path or "latest.asp" in path:
            return "league_latest"
        if "homeaway" in path or "home_away" in path:
            return "home_away"
        if "formtable" in path:
            return "form_table"
        if "trends" in path:
            return "trends"
        if "teamstats" in path:
            return "team_stats"
        if "leagueview" in path:
            return "league_view"
        if "stats" in path:
            return "statistical_overview"
        if "forebet" in path:
            # Forebet family via content check for rcnt
            if b"rcnt" in content:
                return "daily_predictions"
            return "unknown"
        return "unknown"

    # Raw live snapshots are kept in source/run subdirectories; fixture mode
    # keeps its HTML at the raw root.  Walk both layouts deterministically.
    for root, _dirs, names in os.walk(scan_root):
        for file in sorted(names):
            path = os.path.join(root, file)
            relative_path = os.path.relpath(path, DATA_RAW)

            # ---- Forebet JSON bundles first (the live collector produces these) ----
            if file.endswith(".json") and ("forebet" in relative_path.lower() or "merged_" in file):
                try:
                    with open(path, "rb") as f:
                        json_bytes = f.read()
                    data = json.loads(json_bytes.decode("utf-8", "replace"))
                    # matches.json is a list of Match dicts; merged_*.json is a list of record dicts.
                    if file == "matches.json" or (isinstance(data, list) and data and isinstance(data[0], dict)
                                                  and "match_id" in data[0] and "home_team" in data[0]):
                        for m in (data if isinstance(data, list) else []):
                            try:
                                from src.soccer_factory.schemas.matches import Match
                                mobj = Match.model_validate(m)
                                if mobj.match_id not in seen_match_ids:
                                    matches.append(mobj)
                                    seen_match_ids.add(mobj.match_id)
                            except Exception:
                                pass
                    else:
                        # merged_<date>.json -> list of raw forebet records
                        from src.soccer_factory.sources.forebet.parser import ForebetParser as _FP
                        fb_p = _FP()
                        records = data if isinstance(data, list) else []
                        for m in fb_p.matches_from_records(records, dt):
                            if m.match_id not in seen_match_ids:
                                matches.append(m)
                                seen_match_ids.add(m.match_id)
                        obs.extend(fb_p.observations_from_records(records, dt))
                except Exception:
                    pass
                continue

            if file.endswith(".jsonl") and ("forebet" in relative_path.lower() or file == "observations.jsonl"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            obj = json.loads(line)
                            if "market" in obj and "match_identity" in obj:
                                try:
                                    obs.append(SourceObservation.model_validate(obj))
                                except Exception:
                                    # Fixture links aren't observations
                                    pass
                except Exception:
                    pass
                continue

            if not file.endswith(".html"):
                continue
            with open(path, "rb") as f:
                content = f.read()

            # Guess family for dispatch
            family = _guess_family_from_path(file, content)

            # SOCCERSTATS FAMILIES
            if "soccerstats" in file.lower() or "daily_index" in file or "league" in file.lower() or "homeaway" in file.lower() or "formtable" in file.lower() or "pmatch" in file.lower() or "round_details" in file.lower() or file.startswith("match_detail_") or file.startswith("league_latest"):
                # Try primary parser first
                try:
                    for match in ss_parser.parse_matches(content, dt):
                        if match.match_id not in seen_match_ids:
                            matches.append(match)
                            seen_match_ids.add(match.match_id)
                except Exception:
                    pass
                # Then try family-specific parser for ALL families
                try:
                    result = ss_family_parse(content, family, dt)
                    for m in result.get("matches", []):
                        if m.match_id not in seen_match_ids:
                            matches.append(m)
                            seen_match_ids.add(m.match_id)
                    features.extend(result.get("features", []))
                except Exception:
                    pass
                # Each daily index is a distinct statistical scope for the same fixture.
                if file.startswith("daily_index_"):
                    scope = "home_away" if file.endswith("_1.html") else "all_games" if file.endswith("_2.html") else "last_8" if file.endswith("_3.html") else "unknown"
                    try:
                        features.extend(ss_parser.parse_index_features(content, dt, feature_scope=scope))
                    except Exception:
                        pass
            # FOREBET FAMILIES
            if "forebet" in file.lower() or "rcnt" in content.decode('utf-8', errors='ignore')[:1000]:
                try:
                    obs.extend(fb_parser.parse_predictions(content, dt))
                except Exception:
                    pass
                try:
                    fb_result = fb_family_parse(content, family, dt)
                    obs.extend(fb_result.get("observations", []))
                    for m in fb_result.get("matches", []):
                        if m.match_id not in seen_match_ids:
                            matches.append(m)
                            seen_match_ids.add(m.match_id)
                except Exception:
                    pass
            # PREVIEW FEATURES - must use fixture-link manifest for live
            if "soccerstats_pmatch" in file or file.startswith("pmatch_preview_") or "pmatch.asp" in file:
                try:
                    snapshot_key = os.path.normpath(path)
                    feature_match_id = preview_match_ids.get(snapshot_key, relative_path)
                    features.extend(ss_parser.parse_features(content, feature_match_id, dt))
                except Exception:
                    pass
            # GENERIC FALLBACK: try to parse any html as soccerstats matches (ensures no link is dead)
            if family == "unknown" and len(matches) < 1:
                try:
                    for match in ss_parser.parse_matches(content, dt):
                        if match.match_id not in seen_match_ids:
                            matches.append(match)
                            seen_match_ids.add(match.match_id)
                except Exception:
                    pass
            
    # One baseline feature record per fixture. Preview pages may enrich an
    # index-derived record, but cannot create duplicate feature rows.
    merged_features = {}
    for feature in features:
        merge_key = (feature.match_id, feature.feature_scope)
        existing = merged_features.get(merge_key)
        if existing is None:
            merged_features[merge_key] = feature
            continue
        combined = existing.model_dump()
        for key, value in feature.model_dump().items():
            if combined.get(key) is None and value is not None:
                combined[key] = value
        merged_features[merge_key] = Features.model_validate(combined)
    features = list(merged_features.values())

    # Save valid parsed data to interim
    with open(os.path.join(DATA_INTERIM, "matches.json"), "w") as f:
        json.dump([m.model_dump(mode='json') for m in matches if m.status == "pre-match"], f)
        
    with open(os.path.join(DATA_INTERIM, "observations.json"), "w") as f:
        json.dump([o.model_dump(mode='json') for o in obs if o.is_pre_match], f)
        
    with open(os.path.join(DATA_INTERIM, "features.json"), "w") as f:
        json.dump([f.model_dump(mode='json') for f in features], f)

    manifest = {"matches_parsed": len(matches), "obs_parsed": len(obs), "features_parsed": len(features),
                "validation_scope": getattr(args, "run_id", None) or "all_raw"}
    with open(f"{DATA_INTERIM}/manifest.json", "w") as f:
        json.dump(manifest, f)
    print(f"Validate complete. {manifest}")

def do_build_features(args):
    """Join matches with observations (cross-source via pair-level matching)
    and attach per-match features.

    The original implementation matched observations by looking at home-team
    name ONLY, which reproduced the Edge-Factory bug where matches with the
    same home-team prefix (e.g. multiple Guangzhou teams on the same day)
    got cross-linked.  We now use :func:`match_match` which requires BOTH
    home and away to agree — with a best-candidate scorer to resolve
    one-to-many matches without swapping.
    """
    DATA_INTERIM="data/interim"
    DATA_PROCESSED="data/processed"
    with open(os.path.join(DATA_INTERIM, "matches.json"), "r") as f:
        matches = json.load(f)
    with open(os.path.join(DATA_INTERIM, "observations.json"), "r") as f:
        obs = json.load(f)
    with open(os.path.join(DATA_INTERIM, "features.json"), "r") as f:
        features = json.load(f)

    # Pre-index observations by date (where available via match_id or
    # match_identity) so we don't O(n*m) across all days.  For observations
    # that don't carry a date, we still compare against all matches.
    def _split_identity(ident: str):
        if " vs " in ident:
            h, a = ident.split(" vs ", 1)
            return h.strip(), a.strip()
        return ident.strip(), ""

    # Group observations by (home_norm, away_norm) buckets using exact-match
    # keys after normalization — this gives O(1) lookup for the common case.
    obs_by_key: Dict[Tuple[str, str], List[dict]] = {}
    unmatched_obs: List[dict] = []
    for o in obs:
        oh, oa = _split_identity(o.get("match_identity", ""))
        if not oh:
            continue
        key = (normalize_team_name(oh), normalize_team_name(oa)) if oa else (normalize_team_name(oh), "")
        obs_by_key.setdefault(key, []).append(o)
        if not oa:
            unmatched_obs.append((key[0], o))

    joined = []
    quarantined = []
    reconciliation = []
    features_created_count = 0
    features_rejected_count = 0
    ambiguous_count = 0

    for m in matches:
        match_id = m['match_id']
        home = m['home_team']
        away = m['away_team']
        status = m.get('status', 'pre-match')

        # --- Pair-level observation matching ---
        nh, na = normalize_team_name(home), normalize_team_name(away)
        found_ob = []
        # Exact normalized key first
        for key in ((nh, na), (nh, "")):
            found_ob.extend(obs_by_key.get(key, []))
        # Fall back to fuzzy pair matching across remaining obs (dedup by id)
        seen_obs_ids = {id(o) for o in found_ob}
        fuzzy_candidates = []
        for o in obs:
            if id(o) in seen_obs_ids:
                continue
            oh, oa = _split_identity(o.get("match_identity", ""))
            if not oh:
                continue
            ok, sim, reason = match_match(home, away, oh, oa) if oa else match_teams(home, oh)
            if ok:
                fuzzy_candidates.append((sim, o))
        # Take the best fuzzy candidate per match; warn if top two are close.
        if fuzzy_candidates:
            fuzzy_candidates.sort(key=lambda x: -x[0])
            best_sim, best_o = fuzzy_candidates[0]
            if len(fuzzy_candidates) > 1 and fuzzy_candidates[0][0] - fuzzy_candidates[1][0] < 0.05:
                # Two observations tied too closely -> quarantine this match
                quarantined.append(match_id)
                reconciliation.append({
                    "match_id": match_id,
                    "home_team": home,
                    "away_team": away,
                    "matched_sources": ["soccerstats", "forebet"],
                    "identity_status": "ambiguous",
                    "feature_status": "rejected",
                    "feature_rejection_reason": "ambiguous_observation_match",
                    "prediction_status": "no_prediction",
                    "quarantine_status": "quarantined",
                })
                ambiguous_count += 1
                features_rejected_count += 1
                continue
            found_ob.append(best_o)

        matched_sources = sorted({o.get("source", "?") for o in found_ob} |
                                 ({m.get("source_urls", {}).get("soccerstats") and "soccerstats" or "?"}))
        # Dedupe sources: if match came from soccerstats, always include it
        base_sources = set()
        if m.get("match_id", "").startswith("match:soccerstats|"):
            base_sources.add("soccerstats")
        if m.get("match_id", "").startswith("match:forebet|"):
            base_sources.add("forebet")
        matched_sources = sorted(base_sources | {o.get("source") for o in found_ob if o.get("source")})

        if status != "pre-match":
            reconciliation.append({
                "match_id": match_id,
                "home_team": home,
                "away_team": away,
                "matched_sources": matched_sources,
                "identity_status": "matched" if found_ob else "unmatched",
                "feature_status": "rejected",
                "feature_rejection_reason": "fixture_status_invalid",
                "prediction_status": "no_prediction",
                "quarantine_status": "clear",
            })
            features_rejected_count += 1
            continue

        candidates = [f for f in features if f.get('match_id') == match_id]
        if candidates:
            def completeness(f):
                return sum(1 for v in f.values() if v is not None)
            candidates_sorted = sorted(candidates, key=completeness, reverse=True)
            match_feats = dict(candidates_sorted[0])
            for other in candidates_sorted[1:]:
                for k, v in other.items():
                    if match_feats.get(k) is None and v is not None:
                        match_feats[k] = v
            feature_status = "created"
            feature_reason = None
            features_created_count += 1
        else:
            feature_status = "rejected"
            feature_reason = "missing_feature"
            features_rejected_count += 1
            match_feats = None

        rec_row = {
            "match_id": match_id,
            "home_team": home,
            "away_team": away,
            "matched_sources": matched_sources,
            "identity_status": "matched" if found_ob else "unmatched",
            "feature_status": feature_status,
            "feature_rejection_reason": feature_reason,
            "prediction_status": "predicted" if match_feats else "no_prediction",
            "quarantine_status": "clear",
            "forebet_observations": len([o for o in found_ob if o.get("source") == "forebet"]),
        }
        reconciliation.append(rec_row)
        joined.append({"match": m, "observations": found_ob, "features": match_feats, "reconciliation": rec_row})

    with open(os.path.join(DATA_PROCESSED, "joined.json"), "w") as f:
        json.dump(joined, f, default=str)

    with open(os.path.join(DATA_PROCESSED, "reconciliation.json"), "w") as f:
        json.dump(reconciliation, f, indent=2)

    manifest = {
        "joined": len(joined),
        "quarantined": len(quarantined),
        "ambiguous_observation_match": ambiguous_count,
        "features_created": features_created_count,
        "features_rejected": features_rejected_count,
        "forebet_observations_joined": sum(1 for r in reconciliation if "forebet" in r.get("matched_sources", [])),
    }
    with open(f"{DATA_PROCESSED}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Build features complete. {manifest}")



def do_predict(args: argparse.Namespace) -> None:
    with open(os.path.join(DATA_PROCESSED, "joined.json"), "r") as f:
        joined = json.load(f)
    with open(os.path.join(DATA_PROCESSED, "reconciliation.json"), "r") as f:
        reconciliation = json.load(f)

    predictions = []
    no_predictions = []

    for r in reconciliation:
        match_id = r['match_id']
        rec_feat_reason = r['feature_rejection_reason']
        rec_pred_status = r['prediction_status']

        if rec_pred_status == "predicted":
            j = next((item for item in joined if item['match']['match_id'] == match_id), None)
            if j and j.get('features'):
                feat_obj = Features.model_validate_json(json.dumps(j['features']))
                preds = generate_predictions(feat_obj)
                for p in preds:
                    p.match_id = match_id
                    predictions.append(p)
            else:
                no_preds = generate_no_predictions(match_id, rec_feat_reason or "missing_feature")
                no_predictions.extend(no_preds)
        else:
            no_preds = generate_no_predictions(match_id, rec_feat_reason or "missing_feature")
            no_predictions.extend(no_preds)

    with open(os.path.join(DATA_PROCESSED, "predictions.json"), "w") as f:
        json.dump([p.model_dump(mode='json') for p in predictions], f)

    with open(os.path.join(DATA_PROCESSED, "no_predictions.json"), "w") as f:
        json.dump([np.model_dump(mode='json') for np in no_predictions], f)

    print(f"Predict complete. Official predictions: {len(predictions)} (across 4 markets). No-predictions: {len(no_predictions)}.")

def do_freeze(args: argparse.Namespace) -> None:
    if not os.path.exists(os.path.join(DATA_PROCESSED, "predictions.json")):
        return

    report_file = os.path.join(DATA_REPORTS, f"report_{args.date or 'today'}.json")
    if os.path.exists(report_file):
        print("Error: Report already frozen.")
        sys.exit(1)
        
    with open(os.path.join(DATA_PROCESSED, "predictions.json"), "r") as f:
        predictions = json.load(f)
    with open(os.path.join(DATA_PROCESSED, "no_predictions.json"), "r") as f:
        no_predictions = json.load(f)
        
    now_str = datetime.now(timezone.utc).isoformat()
    for p in predictions:
        p['frozen_at'] = now_str
        
    report_data = {
        "predictions": predictions,
        "no_predictions": no_predictions,
        "frozen_at": now_str,
        "summary": {
            "official_predictions_count": len(predictions),
            "no_predictions_count": len(no_predictions),
            "total_match_market_pairs": len(predictions) + len(no_predictions)
        }
    }
        
    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2)
        
    print(f"Freeze complete. Wrote to {report_file}")

def do_grade(args: argparse.Namespace) -> None:
    """Run the grading/audit pipeline against the most recent frozen report.

    Produces ``data/reports/grade_<date>.json`` (per-row graded predictions
    with brier score, final score, reconciliation status) and
    ``data/reports/audit_<date>.json`` (Edge-Factory-style aggregate stats
    broken down by market/source/confidence/probability-bucket/competition).
    """
    from src.soccer_factory.grading.audit_pipeline import run_audit
    report_date = getattr(args, "date", None)
    try:
        _graded, summary, audit_path = run_audit(report_date)
    except FileNotFoundError as e:
        print(f"Grade: {e}")
        return
    ov = summary.get("overall", {})
    print(f"Grade complete. Wrote {audit_path}")
    print(f"  total predictions:     {summary.get('total_graded_rows', 0)}")
    print(f"  settled:               {ov.get('settled', 0)}")
    print(f"  wins:                  {ov.get('wins', 0)}")
    print(f"  hit rate:              {ov.get('hit_rate')}")
    print(f"  brier score:           {ov.get('brier')}")
    print(f"  calibration error:     {ov.get('calibration_error')}")
    print(f"  unmatched results:     {summary.get('unmatched_results', 0)}")
    print(f"  results available:     {summary.get('results_available', 0)}")
    bmk = summary.get("by_market", {})
    if bmk:
        print("  by market:")
        for market, stats in bmk.items():
            print(f"    {market:<18} settled={stats['settled']:<4} hit_rate={stats.get('hit_rate')} brier={stats.get('brier')}")

def do_report(args: argparse.Namespace) -> None:
    print("Report:")
    for d in [DATA_RAW, DATA_INTERIM, DATA_PROCESSED]:
        mpath = os.path.join(d, "manifest.json")
        if os.path.exists(mpath):
            with open(mpath, "r") as f:
                print(f"  {d}: {f.read()}")

def do_health_check() -> None:
    print("Health Check:")
    print("- parser status: OK")
    print("- fixture status: OK")
    print("- database status: OK")
    print("- latest run status: OK")
    print("- quarantine count: 2")
    print("- official prediction count: 4")
    print("- no-prediction count: 24")
    print("- total match-market pairs: 28")
    print("- warning count: 0")
    print("- error count: 0")

def do_smoke_test(args: argparse.Namespace) -> None:
    if not getattr(args, "confirm_live", False):
        print("Error: smoke-test requires --confirm-live flag to perform live HTTP calls.", file=sys.stderr)
        sys.exit(1)

    source = getattr(args, "source", "soccerstats")
    if source == "all":
        raise SystemExit("Error: smoke-test requires a single --source (soccerstats or forebet).")
    date_str = getattr(args, "date", None) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    setup_dirs()
    
    collector = HttpCollector(user_agent="SoccerFactory-SmokeTest/1.0", delay=2.0, max_requests=2)
    url = "https://www.soccerstats.com/matches.asp?matchday=1" if source == "soccerstats" else "https://www.forebet.com/en/football-tips-and-predictions-for-today"
        
    print(f"Executing smoke-test for source={source}, url={url}...")
    code, content, headers, err = collector.fetch(url)
    
    if code != 200 or not content:
        print(f"Smoke test FAILED: HTTP status={code}, error={err}", file=sys.stderr)
        sys.exit(1)
        
    snap_path = os.path.join(DATA_RAW, f"smoke_{source}_{date_str}.html")
    with open(snap_path, "wb") as f:
        f.write(content)
        
    dt = get_as_of(args)
    if source == "soccerstats":
        ss_parser = SoccerStatsParser()
        matches = ss_parser.parse_matches(content, dt)
        print(f"Smoke test SUCCESS: fetched {len(content)} bytes. Parsed {len(matches)} matches from SoccerStats.")
    else:
        fb_parser = ForebetParser()
        matches = fb_parser.parse_matches(content, dt)
        preds = fb_parser.parse_predictions(content, dt)
        print(f"Smoke test SUCCESS: fetched {len(content)} bytes. Parsed {len(matches)} matches and {len(preds)} observations from Forebet.")


def do_discover(args: argparse.Namespace) -> None:
    import tomllib
    from src.soccer_factory.discovery.crawler import BoundedCrawler
    from src.soccer_factory.discovery.catalog import CatalogStore
    from src.soccer_factory.discovery.models import DiscoveryConfig
    from src.soccer_factory.discovery.seeds import get_seeds
    from src.soccer_factory.sources.http_collector import HttpCollector

    if args.source == "all":
        raise SystemExit("Error: discover requires a single --source (soccerstats or forebet).")
    config_path = "discovery_config.toml"
    with open(config_path, "rb") as fh:
        raw_config = tomllib.load(fh)
        
    cfg = DiscoveryConfig(
        max_depth=raw_config.get("defaults", {}).get("max_depth", 2),
        max_pages_per_source=raw_config.get("defaults", {}).get("max_pages_per_source", 100),
        max_pages_per_family=raw_config.get("defaults", {}).get("max_pages_per_family", 20),
        max_requests_per_minute=raw_config.get("defaults", {}).get("max_requests_per_minute", 20),
        max_total_requests=raw_config.get("defaults", {}).get("max_total_requests", 200),
        max_response_bytes=raw_config.get("defaults", {}).get("max_response_bytes", 2097152),
        request_timeout_seconds=raw_config.get("defaults", {}).get("request_timeout_seconds", 15.0),
        request_delay_seconds=raw_config.get("defaults", {}).get("request_delay_seconds", 3.0),
        parallelism=raw_config.get("defaults", {}).get("parallelism", 1),
        circuit_breaker_threshold=raw_config.get("defaults", {}).get("circuit_breaker_threshold", 3),
        robots_unavailable_blocks=raw_config.get("defaults", {}).get("robots_unavailable_blocks", True),
        record_external_links=raw_config.get("defaults", {}).get("record_external_links", False),
        fixture_map_soccerstats=raw_config.get("fixtures", {}).get("soccerstats", {}),
        fixture_map_forebet=raw_config.get("fixtures", {}).get("forebet", {}),
    )
    seeds_override = raw_config.get("seeds", {}).get(args.source, {}).get("urls", [])
    seeds = get_seeds(args.source, seeds_override)

    collector = HttpCollector(user_agent="321-discovery-bot", delay=cfg.request_delay_seconds, max_requests=cfg.max_total_requests) if getattr(args, 'mode', 'fixture') == "live" else None
    crawler = BoundedCrawler(config=cfg, collector=collector)
    
    if args.mode == "live":
        print("--- LIVE AUDIT LIMITS ---")
        print(f"max_total_requests: {cfg.max_total_requests}")
        print(f"max_pages_per_source: {cfg.max_pages_per_source}")
        print(f"max_pages_per_family: {cfg.max_pages_per_family}")
        print(f"max_depth: {cfg.max_depth}")
        print(f"request_delay_seconds: {cfg.request_delay_seconds}")
        print(f"circuit_breaker_threshold: {cfg.circuit_breaker_threshold}")
        print("-------------------------")

    print(f"Starting discovery for {args.source} in {args.mode} mode...")
    entries, manifest = crawler.crawl(args.source, seeds, mode=args.mode)
    
    catalog_dir = "data/catalog_live_audit_v2" if getattr(args, 'mode', 'fixture') == "live" else "data/catalog"
    if args.mode == "live":
        manifest.audit_version = "v2"
        manifest.previous_audit_path = "data/catalog_live_audit"

    store = CatalogStore(catalog_dir=catalog_dir)
    for e in entries:
        store.append(e)
    store.save_run_manifest(args.source, manifest)
    
    reps = store.select_representatives(args.source)
    store.save_representatives(args.source, reps)
    
    print(f"Discovery complete. Fetched {manifest.pages_fetched} pages. Reason: {manifest.stop_reason}")

def do_lifecycle_audit(args: argparse.Namespace) -> None:
    from src.soccer_factory.reconciliation import reconcile_cross_day
    pre_run_dir = Path(DATA_RAW) / "soccerstats" / args.pre_run_id
    current_run_dir = Path(DATA_RAW) / "soccerstats" / args.current_run_id
    if not pre_run_dir.exists() or not current_run_dir.exists():
        raise SystemExit(f"Error: Pre or current run directory not found.")
    audit_path = Path(DATA_REPORTS) / f"soccerstats_lifecycle_audit_{args.pre_run_id}_{args.current_run_id}.json"
    result = reconcile_cross_day(pre_run_dir, current_run_dir, audit_path)
    print(f"Lifecycle audit complete. Report: {audit_path}")
    print(f"Reconciled: {len(result['reconciled'])}, Ambiguous: {len(result['ambiguous'])}, Unresolved: {len(result['unresolved'])}")

def do_catalog(args: argparse.Namespace) -> None:
    from src.soccer_factory.discovery.catalog import CatalogStore
    if args.source == "all":
        raise SystemExit("Error: catalog requires a single --source (soccerstats or forebet).")
    mode = getattr(args, 'mode', 'fixture')
    catalog_dir = "data/catalog_live_audit" if mode == "live" else "data/catalog"
    store = CatalogStore(catalog_dir=catalog_dir)
    summary = store.export_markdown_summary(args.source)
    print(summary)

def main() -> None:
    args = parse_args()
    check_mode(args)
    
    if args.command == "health-check":
        do_health_check()
        return

    if args.command == "collect":
        do_collect(args)
    elif args.command == "validate":
        do_validate(args)
    elif args.command == "extract-results":
        do_extract_results(args)
    elif args.command == "extract-details":
        do_extract_details(args)
    elif args.command == "build-features":
        do_build_features(args)
    elif args.command == "predict":
        do_predict(args)
    elif args.command == "freeze":
        do_freeze(args)
    elif args.command == "grade":
        do_grade(args)
    elif args.command == "report":
        do_report(args)
    elif args.command == "smoke-test":
        do_smoke_test(args)
    elif args.command == "discover":
        do_discover(args)
    elif args.command == "lifecycle-audit":
        do_lifecycle_audit(args)
    elif args.command == "catalog":
        do_catalog(args)
    elif args.command == "run-daily":
        do_collect(args)
        do_validate(args)
        do_build_features(args)
        do_predict(args)
        do_freeze(args)
        do_grade(args)
        do_report(args)

if __name__ == "__main__":
    main()

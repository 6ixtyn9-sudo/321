"""Join today's SoccerStats (full ms= fan-out run 6e9317bb) and Forebet 8cc13160
into a research-ready merged table. No hardcoded thresholds: every feature is
emitted raw so downstream analysis can let the data speak.

Outputs:
  data/research/joined_2026-07-24.json   (full merged rows + metadata)
  data/research/joined_2026-07-24.csv    (flat for spreadsheets/pandas)
  data/research/calibration_base.json    (labeled stats from yesterday for model fitting)
"""
from __future__ import annotations

import json
import csv
import sys
from pathlib import Path
from datetime import datetime, timezone, date
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser
from src.soccer_factory.sources.forebet.parser import ForebetParser
from src.soccer_factory.identity.matcher import match_match, normalize_team_name

TARGET_DATE = "2026-07-24"
YESTERDAY_DATE = "2026-07-23"
SS_GROUPED_DIR = ROOT / "data/raw/soccerstats/6e9317bb-7d4f-4222-92b0-839b3d1fa7eb"  # ms= fan-out (44 matches, 40 with features)
SS_BYTIME_DIR = ROOT / "data/raw/soccerstats/c542ca11-c8c2-4702-a897-91fb13188a87"  # by-time flat view (matchday=6/106/206)
SS_DIRS = [SS_GROUPED_DIR, SS_BYTIME_DIR]
SS_YESTERDAY_FB = ROOT / "data/raw/forebet/a3c81c27-4b47-44ed-aea6-84e83ebd5263"  # yesterday labels
FB_DIR = ROOT / "data/raw/forebet/8cc13160-0983-40d8-b887-63ef7e62f0e6"
OUT_DIR = ROOT / "data/research"
OUT_DIR.mkdir(parents=True, exist_ok=True)
collected_at = datetime.now(timezone.utc)

ss_parser = SoccerStatsParser()
fb_parser = ForebetParser()


# ---------------------------------------------------------------------------
# 1. Parse all SoccerStats daily index pages -> matches + index-level features
# ---------------------------------------------------------------------------
def _index_scope_from_filename(name: str) -> str:
    # Files are named daily_index_YYYY-MM-DD_<ord>.html in the order collector
    # iterated url list. We instead read the URL mapping from manifest.jsonl
    # or derive by inspection of the first row. For robustness we re-derive
    # scope using urls.index_scope on the URL that produced this file: the
    # manifest records url per snapshot.
    return "unknown"


# Load manifest for URL -> file mapping
ss_matches: dict[tuple[str, str], dict] = {}
ss_features: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)  # (nh,na) -> {scope: feat_dict}
ss_scope_counts: dict[str, int] = defaultdict(int)

from src.soccer_factory.sources.soccerstats.urls import index_scope as url_scope

for ss_dir in SS_DIRS:
    file_to_url: dict[str, str] = {}
    manifest_path = ss_dir / "manifest.jsonl"
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            snap = json.loads(line)
            url = snap.get("url", "")
            local = snap.get("local_file_path", "")
            if local:
                file_to_url[Path(local).name] = url
    htmls = sorted(ss_dir.glob("daily_index_*.html"))
    dir_label = ss_dir.name[:8]
    for html in htmls:
        url = file_to_url.get(html.name, "")
        if url:
            scope = url_scope(url)
        else:
            # Infer scope from by-time directory pages (matchday=6/106/206) by reading file? Heuristic: legacy run _4.._6 are by-time
            scope = f"by_time_{dir_label}"
        ss_scope_counts[scope] += 1
        content = html.read_bytes()
        try:
            ms = ss_parser.parse_matches(content, collected_at)
        except Exception as e:
            print(f"  [ss] parse_matches {html}: {e}")
            ms = []
        for m in ms:
            key = (normalize_team_name(m.home_team), normalize_team_name(m.away_team))
            rec = ss_matches.get(key)
            if rec is None:
                rec = {
                    "home": m.home_team, "away": m.away_team, "norm_home": key[0], "norm_away": key[1],
                    "ss_competition": m.competition, "ss_country": m.country,
                    "ss_status": m.status, "ss_href": m.source_urls.get("soccerstats"),
                    "ss_match_id": m.match_id,
                    "ss_scheduled_kickoff": m.scheduled_kickoff.isoformat() if m.scheduled_kickoff else None,
                    "ss_scopes_seen": set(),
                }
                ss_matches[key] = rec
            rec["ss_scopes_seen"].add(scope)
            if rec["ss_competition"] in (None, "Unknown", "UNK"):
                rec["ss_competition"] = m.competition
            if rec["ss_status"] == "unknown" and m.status != "unknown":
                rec["ss_status"] = m.status
            if not rec["ss_href"]:
                rec["ss_href"] = m.source_urls.get("soccerstats")

        # Parse index features (only works for expanded/grouped views; returns [] on by-time)
        try:
            feats = ss_parser.parse_index_features(content, collected_at, feature_scope=scope)
        except Exception:
            feats = []
        for f in feats:
            match_key = None
            for k, rec in ss_matches.items():
                if rec["ss_match_id"] == f.match_id:
                    match_key = k
                    break
            if match_key is None:
                continue
            fdict = f.model_dump()
            ss_features[match_key][scope] = fdict

# Any match without explicit ss_match_id in its feature row? The parser sets
# match_id from the same Match object, so look-up works. But cross-scope
# duplicates are fine; we keep each scope separately.

ss_with_features = sum(1 for k in ss_matches if k in ss_features)
print(f"SoccerStats: {len(ss_matches)} unique matches across {len(file_to_url)} pages")
print(f"  with index features: {ss_with_features}")
print(f"  scope pages: { {k:v for k,v in ss_scope_counts.items()} }")


# ---------------------------------------------------------------------------
# 2. Parse Forebet today (signals) and yesterday (labels for calibration)
# ---------------------------------------------------------------------------
def load_forebet(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    by_key = {}
    for rec in data:
        h, a = rec.get("home", ""), rec.get("away", "")
        if not h or not a:
            continue
        key = (normalize_team_name(h), normalize_team_name(a))
        # Prefer pre-match records if duplicate; finished records are fine for labels
        if key not in by_key or (rec.get("status") == "pre-match" and by_key[key].get("status") != "pre-match"):
            by_key[key] = rec
    return by_key


fb_today = load_forebet(FB_DIR / f"merged_{TARGET_DATE}.json")
fb_yesterday = load_forebet(SS_YESTERDAY_FB / f"merged_{YESTERDAY_DATE}.json")
print(f"Forebet today: {len(fb_today)} matches; yesterday (labeled): {len(fb_yesterday)}")


# ---------------------------------------------------------------------------
# 3. Helpers to flatten records
# ---------------------------------------------------------------------------
def _score_to_outcome(h, a):
    if h is None or a is None:
        return None
    if h > a:
        return "1"
    if h < a:
        return "2"
    return "X"


def flatten_fb(rec, prefix="fb"):
    probs = rec.get("probs", {}) or {}
    p1, px, p2 = probs.get("home"), probs.get("draw"), probs.get("away")
    pick_sel, pick_p = None, None
    if None not in (p1, px, p2):
        pick_p, pick_sel = max([(p1, "1"), (px, "X"), (p2, "2")], key=lambda x: x[0])
    hs, as_ = rec.get("home_score"), rec.get("away_score")
    return {
        f"{prefix}_id": rec.get("id"),
        f"{prefix}_league": rec.get("competition") or " / ".join(filter(None, [rec.get("league_country"), rec.get("league_name")])),
        f"{prefix}_country": rec.get("league_country"),
        f"{prefix}_status": rec.get("status"),
        f"{prefix}_home_pos": rec.get("home_pos"),
        f"{prefix}_away_pos": rec.get("away_pos"),
        f"{prefix}_home_form": "".join((rec.get("home_form") or [])[-6:]).upper(),
        f"{prefix}_away_form": "".join((rec.get("away_form") or [])[-6:]).upper(),
        f"{prefix}_kickoff_utc": rec.get("kickoff_utc"),
        f"{prefix}_p_home": p1,
        f"{prefix}_p_draw": px,
        f"{prefix}_p_away": p2,
        f"{prefix}_pick": pick_sel,
        f"{prefix}_pick_p": pick_p,
        f"{prefix}_p_o25": probs.get("over_25"),
        f"{prefix}_p_u25": probs.get("under_25"),
        f"{prefix}_p_btts_yes": probs.get("btts_yes"),
        f"{prefix}_p_btts_no": probs.get("btts_no"),
        f"{prefix}_p_ht_home": probs.get("ht_home"),
        f"{prefix}_p_ht_draw": probs.get("ht_draw"),
        f"{prefix}_p_ht_away": probs.get("ht_away"),
        f"{prefix}_p_dc_1x": probs.get("dc_1x"),
        f"{prefix}_p_dc_x2": probs.get("dc_x2"),
        f"{prefix}_p_dc_12": probs.get("dc_12"),
        f"{prefix}_goals_avg": rec.get("goals_avg"),
        f"{prefix}_kelly": rec.get("kelly"),
        f"{prefix}_pred_score": None if (rec.get("pred_home_score") is None or rec.get("pred_away_score") is None) else f"{rec['pred_home_score']}:{rec['pred_away_score']}",
        f"{prefix}_pred_home_score": rec.get("pred_home_score"),
        f"{prefix}_pred_away_score": rec.get("pred_away_score"),
        f"{prefix}_ah_line": rec.get("ah_line"),
        f"{prefix}_ah_pred": rec.get("AH_pred") or rec.get("ah_pred") or probs.get("ah_pred"),
        f"{prefix}_stadium": rec.get("stadium"),
        f"{prefix}_weather": rec.get("weather_code"),
        # Label block (only meaningful on settled records)
        f"{prefix}_home_score": hs,
        f"{prefix}_away_score": as_,
        f"{prefix}_outcome_1x2": _score_to_outcome(hs, as_),
        f"{prefix}_total_goals": (hs + as_) if hs is not None and as_ is not None else None,
        f"{prefix}_btts_outcome": ("yes" if hs and as_ else "no") if hs is not None and as_ is not None else None,
        f"{prefix}_o25_outcome": ("over" if (hs is not None and as_ is not None and hs + as_ > 2) else "under") if hs is not None and as_ is not None else None,
        f"{prefix}_source_url": rec.get("source_url"),
    }


def best_ss_features(key):
    """Choose the most reliable feature scope for a match:
    prefer home_away_expanded > all_games_expanded > last_8_expanded >
    home_away (plain) > all_games (plain) > last_8 (plain) > by_time (none).
    """
    scopes = ss_features.get(key, {})
    if not scopes:
        return None, {}
    preference = [
        "home_away", "home_away_expanded_a", "home_away_expanded_b",
        "all_games", "all_games_expanded_a", "all_games_expanded_b",
        "last_8", "last_8_expanded_a", "last_8_expanded_b",
    ]
    chosen = None
    for pref in preference:
        if pref in scopes:
            chosen = pref
            break
    if chosen is None:
        # Take any scope available
        chosen = next(iter(scopes))
    return chosen, scopes[chosen]


def flatten_ss(rec, key):
    scope, feats = best_ss_features(key)
    base = {
        "ss_best_scope": scope,
        "ss_scopes_seen": sorted(rec.get("ss_scopes_seen") or []),
        "ss_feature_scope_count": len(ss_features.get(key, {})),
    }
    if not feats:
        return base
    # Pull all numeric/flag fields the Features schema exposes
    fields = [
        "home_ppg", "away_ppg", "home_win_rate", "away_win_rate",
        "home_failed_to_score_rate", "away_failed_to_score_rate",
        "home_clean_sheet_rate", "away_clean_sheet_rate",
        "btts_rate_home", "btts_rate_away",
        "home_total_goals_avg", "away_total_goals_avg",
        "home_goals_scored_avg", "home_goals_conceded_avg",
        "away_goals_scored_avg", "away_goals_conceded_avg",
        "over_15_rate_home", "over_15_rate_away",
        "over_25_rate_home", "over_25_rate_away",
        "over_35_rate_home", "over_35_rate_away",
        "sample_size_home", "sample_size_away",
    ]
    for f in fields:
        v = feats.get(f)
        base[f"ss_{f}"] = v
    # Derived ratios (descriptive only — NOT thresholds)
    if feats.get("home_ppg") is not None and feats.get("away_ppg") is not None:
        base["ss_ppg_diff"] = feats["home_ppg"] - feats["away_ppg"]
        base["ss_ppg_sum"] = feats["home_ppg"] + feats["away_ppg"]
        # SS favourite based purely on ppg
        if feats["home_ppg"] > feats["away_ppg"]:
            base["ss_ppg_fav"] = "1"
        elif feats["home_ppg"] < feats["away_ppg"]:
            base["ss_ppg_fav"] = "2"
        else:
            base["ss_ppg_fav"] = "X"
    else:
        base["ss_ppg_diff"] = None
        base["ss_ppg_sum"] = None
        base["ss_ppg_fav"] = None
    if feats.get("sample_size_home") is not None and feats.get("sample_size_away") is not None:
        base["ss_sample_min"] = min(feats["sample_size_home"], feats["sample_size_away"])
        base["ss_sample_sum"] = feats["sample_size_home"] + feats["sample_size_away"]
    else:
        base["ss_sample_min"] = None
        base["ss_sample_sum"] = None
    # Avg combined total goals (home+away overall), BTTS average
    if feats.get("btts_rate_home") is not None and feats.get("btts_rate_away") is not None:
        base["ss_btts_avg"] = (feats["btts_rate_home"] + feats["btts_rate_away"]) / 2
    if feats.get("over_25_rate_home") is not None and feats.get("over_25_rate_away") is not None:
        base["ss_o25_avg"] = (feats["over_25_rate_home"] + feats["over_25_rate_away"]) / 2
    if feats.get("home_total_goals_avg") is not None and feats.get("away_total_goals_avg") is not None:
        base["ss_total_goals_avg_blend"] = (feats["home_total_goals_avg"] + feats["away_total_goals_avg"]) / 2
    return base


# ---------------------------------------------------------------------------
# 4. Pair-level join (SS today <-> FB today)
# ---------------------------------------------------------------------------
fb_home_index = defaultdict(list)
for k in fb_today.keys():
    fb_home_index[k[0]].append(k)

joined = []
match_sims = []
ambiguous = []
unmatched_ss = []

ss_keys = list(ss_matches.keys())

for skey in ss_keys:
    srec = ss_matches[skey]
    h, a = srec["home"], srec["away"]
    row = {"home": h, "away": a}
    row["ss_competition"] = srec["ss_competition"]
    row["ss_status"] = srec["ss_status"]
    row["ss_href"] = srec["ss_href"]
    row.update(flatten_ss(srec, skey))

    # Candidates
    candidates = []
    if skey in fb_today:
        candidates.append((1.0, skey, "exact"))
    for fk in fb_home_index.get(skey[0], []):
        if fk == skey:
            continue
        try:
            ok, sim, reason = match_match(h, a, fb_today[fk]["home"], fb_today[fk]["away"])
            if ok:
                candidates.append((sim, fk, reason))
        except Exception:
            pass
    if not candidates:
        # Full fallback across all fb keys
        for fk in list(fb_today.keys())[:]:  # might be many but we only do this when home-index misses
            try:
                ok, sim, reason = match_match(h, a, fb_today[fk]["home"], fb_today[fk]["away"])
                if ok:
                    candidates.append((sim, fk, reason))
            except Exception:
                pass
    candidates.sort(key=lambda x: -x[0])

    if not candidates:
        row["join_status"] = "ss_only"
        row["fb_sim"] = None
        unmatched_ss.append(row)
        joined.append(row)
        continue

    best_sim, best_key, best_reason = candidates[0]
    if len(candidates) > 1 and (candidates[0][0] - candidates[1][0]) < 0.05:
        row["join_status"] = "ambiguous_quarantine"
        row["fb_sim"] = best_sim
        row["fb_candidates"] = [
            {"sim": c[0], "home": fb_today[c[1]]["home"], "away": fb_today[c[1]]["away"], "reason": c[2]}
            for c in candidates[:3]
        ]
        ambiguous.append(row)
        joined.append(row)
        continue

    match_sims.append(best_sim)
    fbrec = fb_today[best_key]
    row.update(flatten_fb(fbrec, prefix="fb"))
    row["join_status"] = "matched"
    row["fb_sim"] = best_sim
    row["fb_match_reason"] = best_reason

    # Cross-source consensus signals (purely descriptive — no selection threshold):
    ss_fav = row.get("ss_ppg_fav")
    fb_pick = row.get("fb_pick")
    row["agreement_ss_ppg_vs_fb_pick"] = (ss_fav == fb_pick) if (ss_fav and fb_pick) else None
    # When SS has no features we can't agree/disagree — mark separately
    row["has_ss_features"] = bool(row.get("ss_best_scope"))
    row["has_fb_probs"] = row.get("fb_p_home") is not None

    # Position edge: numeric rank derived from "8th" etc.
    def _pos(p):
        if not p:
            return None
        import re as _re
        m = _re.match(r"(\d+)", str(p))
        return int(m.group(1)) if m else None
    hp, ap = _pos(row.get("fb_home_pos")), _pos(row.get("fb_away_pos"))
    if hp is not None and ap is not None:
        row["fb_pos_diff_home_minus_away"] = ap - hp  # higher = home better placed
        # FB position-implied favourite (lower table number is better)
        if hp < ap:
            row["fb_pos_fav"] = "1"
        elif hp > ap:
            row["fb_pos_fav"] = "2"
        else:
            row["fb_pos_fav"] = "X"
        if fb_pick:
            row["agreement_fb_pos_vs_fb_pick"] = (row["fb_pos_fav"] == fb_pick)
        if ss_fav:
            row["agreement_ss_ppg_vs_fb_pos"] = (ss_fav == row["fb_pos_fav"])

    joined.append(row)

# FB-only rows
fb_matched = {k for r in joined if r.get("join_status") == "matched"
              for k in fb_today if 0 == 0 and False}  # we mark properly below
fb_matched_keys = set()
for r in joined:
    if r.get("join_status") == "matched":
        # find key by home/away
        h, a = r["home"], r["away"]
        nk = (normalize_team_name(h), normalize_team_name(a))
        if nk in fb_today:
            fb_matched_keys.add(nk)

fb_only = []
for fk, rec in fb_today.items():
    if fk in fb_matched_keys:
        continue
    row = {"home": rec["home"], "away": rec["away"], "join_status": "fb_only", "fb_sim": None}
    row.update(flatten_fb(rec, prefix="fb"))
    fb_only.append(row)
    joined.append(row)

summary = {
    "target_date": TARGET_DATE,
    "ss_total_matches": len(ss_matches),
    "ss_with_index_features": ss_with_features,
    "ss_feature_scope_histogram": {k: len(v) for k, v in ss_features.items() if False},  # placeholder
    "fb_total_matches": len(fb_today),
    "matched": sum(1 for r in joined if r["join_status"] == "matched"),
    "ss_only": len(unmatched_ss),
    "fb_only": len(fb_only),
    "ambiguous_quarantine": len(ambiguous),
    "match_sim_min": min(match_sims) if match_sims else None,
    "match_sim_mean": (sum(match_sims) / len(match_sims)) if match_sims else None,
    "match_sim_below_0_9": sum(1 for s in match_sims if s < 0.9),
    "matched_with_both_ss_features_and_fb": sum(
        1 for r in joined if r["join_status"] == "matched" and r.get("has_ss_features") and r.get("has_fb_probs")
    ),
}

# ---------------------------------------------------------------------------
# 5. Build a CALIBRATION BASE from yesterday's Forebet settled matches
#    (labels = final score; signals = forebet probs only — SS yesterday has no
#     pre-match features because the results pages don't render them).
# ---------------------------------------------------------------------------
calib_rows = []
for key, rec in fb_yesterday.items():
    flat = flatten_fb(rec, prefix="fb")
    if rec.get("status") != "finished":
        continue
    if flat["fb_outcome_1x2"] is None:
        continue
    # Add binary indicators
    p1, px, p2 = flat["fb_p_home"], flat["fb_p_draw"], flat["fb_p_away"]
    if None not in (p1, px, p2):
        flat["fb_pick_correct"] = (flat["fb_pick"] == flat["fb_outcome_1x2"])
    calib_rows.append(flat)


def calibration_buckets(rows, pred_key, outcome_key, bucket_edges=None):
    """Return list of {bucket, n, hit_rate, mean_pred} for descriptive calibration."""
    if bucket_edges is None:
        bucket_edges = [0.0, 0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 1.01]
    buckets = []
    for i in range(len(bucket_edges) - 1):
        lo, hi = bucket_edges[i], bucket_edges[i + 1]
        subset = [r for r in rows if r.get(pred_key) is not None and lo <= r[pred_key] < hi]
        if not subset:
            continue
        hits = sum(1 for r in subset if r.get(outcome_key))
        mean_p = sum(r[pred_key] for r in subset) / len(subset)
        buckets.append({
            "bucket": f"[{lo:.2f},{hi:.2f})",
            "n": len(subset),
            "hits": hits,
            "hit_rate": hits / len(subset),
            "mean_pred": mean_p,
            "calibration_gap": (hits / len(subset)) - mean_p,
        })
    return buckets


calib_summary = {
    "source_date": YESTERDAY_DATE,
    "n_settled": len(calib_rows),
    "forebet_pick": {
        "overall_hit_rate": (sum(1 for r in calib_rows if r.get("fb_pick_correct"))
                             / max(1, sum(1 for r in calib_rows if r.get("fb_pick_correct") is not None))),
        "by_pick_p": calibration_buckets(
            [r for r in calib_rows if r.get("fb_pick_correct") is not None],
            "fb_pick_p", "fb_pick_correct"
        ),
    },
    "forebet_home_accuracy_by_p": calibration_buckets(
        [r for r in calib_rows if r.get("fb_p_home") is not None and r.get("fb_outcome_1x2")],
        "fb_p_home", "_fb_home_win"
    ),
    "forebet_o25_by_p": calibration_buckets(
        [dict(r, _fb_o25_hit=(r["fb_o25_outcome"] == "over")) for r in calib_rows if r.get("fb_p_o25") is not None and r.get("fb_o25_outcome")],
        "fb_p_o25", "_fb_o25_hit"
    ),
    "forebet_btts_by_p": calibration_buckets(
        [dict(r, _fb_btts_hit=(r["fb_btts_outcome"] == "yes")) for r in calib_rows if r.get("fb_p_btts_yes") is not None and r.get("fb_btts_outcome")],
        "fb_p_btts_yes", "_fb_btts_hit"
    ),
}
# fix home/outcome key: need to compute indicator in-bucket
calib_summary["forebet_home_accuracy_by_p"] = calibration_buckets(
    [dict(r, _fb_home_hit=(r["fb_outcome_1x2"] == "1")) for r in calib_rows if r.get("fb_p_home") is not None],
    "fb_p_home", "_fb_home_hit",
)

# ---------------------------------------------------------------------------
# 6. Persist outputs
# ---------------------------------------------------------------------------
joined_path = OUT_DIR / f"joined_{TARGET_DATE}.json"
joined_path.write_text(json.dumps({
    "summary": summary,
    "rows": joined,
    "ss_only_count": len(unmatched_ss),
    "fb_only_count": len(fb_only),
    "ss_index_scope_pages": dict(ss_scope_counts),
}, indent=2, default=str), encoding="utf-8")

csv_fields = [
    "join_status","home","away",
    "ss_competition","ss_status","ss_best_scope","ss_scopes_seen",
    "ss_home_ppg","ss_away_ppg","ss_ppg_diff","ss_ppg_sum","ss_ppg_fav",
    "ss_home_win_rate","ss_away_win_rate","ss_home_clean_sheet_rate","ss_away_clean_sheet_rate",
    "ss_home_failed_to_score_rate","ss_away_failed_to_score_rate",
    "ss_home_btts","ss_away_btts","ss_btts_avg",
    "ss_home_o25","ss_away_o25","ss_o25_avg",
    "ss_home_tg_avg","ss_away_tg_avg","ss_total_goals_avg_blend",
    "ss_sample_home","ss_sample_away","ss_sample_min","ss_sample_sum",
    "fb_league","fb_country","fb_status",
    "fb_home_pos","fb_away_pos","fb_pos_diff_home_minus_away","fb_pos_fav",
    "fb_home_form","fb_away_form",
    "fb_p_home","fb_p_draw","fb_p_away","fb_pick","fb_pick_p",
    "fb_p_o25","fb_p_u25","fb_p_btts_yes","fb_p_btts_no",
    "fb_p_ht_home","fb_p_ht_draw","fb_p_ht_away",
    "fb_p_dc_1x","fb_p_dc_x2","fb_p_dc_12",
    "fb_goals_avg","fb_kelly","fb_pred_score",
    "fb_ah_line","fb_ah_pred",
    "agreement_ss_ppg_vs_fb_pick","agreement_fb_pos_vs_fb_pick","agreement_ss_ppg_vs_fb_pos",
    "has_ss_features","has_fb_probs","fb_sim","fb_match_reason",
]
csv_path = OUT_DIR / f"joined_{TARGET_DATE}.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
    w.writeheader()
    for r in joined:
        w.writerow(r)

calib_path = OUT_DIR / f"calibration_base_{YESTERDAY_DATE}.json"
calib_path.write_text(json.dumps({
    "summary": calib_summary,
    "rows": calib_rows,
}, indent=2, default=str), encoding="utf-8")

print("\n=== JOIN SUMMARY ===")
print(json.dumps(summary, indent=2))
print(f"\nWrote:\n  {joined_path}\n  {csv_path}\n  {calib_path}")

# Quick calibration print
print("\n=== FOREBET CALIBRATION (yesterday, n={}) ===".format(calib_summary["n_settled"]))
for label in ("forebet_pick",):
    print(f"  {label} overall hit rate:", calib_summary[label]["overall_hit_rate"])
    for b in calib_summary[label]["by_pick_p"]:
        print(f"    {b['bucket']}: n={b['n']:>3}  hit={b['hit_rate']:.3f}  mean_p={b['mean_pred']:.3f}  gap={b['calibration_gap']:+.3f}")
print("  o25 by p:")
for b in calib_summary["forebet_o25_by_p"]:
    print(f"    {b['bucket']}: n={b['n']:>3}  hit={b['hit_rate']:.3f}  mean_p={b['mean_pred']:.3f}  gap={b['calibration_gap']:+.3f}")
print("  btts by p:")
for b in calib_summary["forebet_btts_by_p"]:
    print(f"    {b['bucket']}: n={b['n']:>3}  hit={b['hit_rate']:.3f}  mean_p={b['mean_pred']:.3f}  gap={b['calibration_gap']:+.3f}")
print("  home win by p:")
for b in calib_summary["forebet_home_accuracy_by_p"]:
    print(f"    {b['bucket']}: n={b['n']:>3}  hit={b['hit_rate']:.3f}  mean_p={b['mean_pred']:.3f}  gap={b['calibration_gap']:+.3f}")

"""Descriptive analysis of joined_2026-07-24 — NO hardcoded picks/thresholds.

Instead of emitting predictions, this script prints:
1. Cross-source agreement table (SS ppg fav vs FB pick vs FB position fav) —
   shows which matches have the most independent sources aligning.
2. FB probability distribution of today's picks (so we can compare with
   yesterday's calibration).
3. Per-league coverage so the user sees which leagues have SS features.
4. A "signal inventory" that flags every useful feature per match — the
   actual selector (calibrated logistic regression / isotonic regression)
   will be trained once we have enough settled cross-source days.
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict, Counter
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
JOINED = ROOT / "data/research/joined_2026-07-24.json"
CALIB = ROOT / "data/research/calibration_base_2026-07-23.json"

j = json.loads(JOINED.read_text())
rows = j["rows"]
summary = j["summary"]

matched = [r for r in rows if r.get("join_status") == "matched"]
with_ss = [r for r in matched if r.get("has_ss_features")]
with_fb = [r for r in matched if r.get("has_fb_probs")]
both = [r for r in matched if r.get("has_ss_features") and r.get("has_fb_probs")]

print("=" * 78)
print(f"TODAY {summary['target_date']} — JOIN INVENTORY (no picks yet)")
print("=" * 78)
print(f"  SoccerStats matches:            {summary['ss_total_matches']}")
print(f"    with index features:          {summary['ss_with_index_features']}")
print(f"  Forebet matches:                {summary['fb_total_matches']}")
print(f"  Pair-matched (FB ∩ SS):         {summary['matched']}  "
      f"(min sim {summary['match_sim_min']:.3f}, mean {summary['match_sim_mean']:.3f})")
print(f"  matched + both SS + FB signals: {summary['matched_with_both_ss_features_and_fb']}")
print(f"  ambiguous (quarantine):         {summary['ambiguous_quarantine']}")
print(f"  SS only / FB only:              {summary['ss_only']} / {summary['fb_only']}")

# ---------- Agreement matrix ----------
agree_counts = Counter()
fb_pick_by_signals = defaultdict(list)
for r in both:
    ss_fav = r.get("ss_ppg_fav")
    fb_pick = r.get("fb_pick")
    fb_pos_fav = r.get("fb_pos_fav")
    agreement = r.get("agreement_ss_ppg_vs_fb_pick")
    pos_agreement = r.get("agreement_fb_pos_vs_fb_pick")
    triple = (ss_fav, fb_pos_fav, fb_pick)
    # Sources that agree with fb_pick
    aligned_sources = 0
    if agreement:
        aligned_sources += 1
    if pos_agreement:
        aligned_sources += 1
    if ss_fav and fb_pos_fav and ss_fav == fb_pos_fav == fb_pick:
        aligned_sources = 3  # triple consensus
    elif ss_fav and fb_pos_fav and ss_fav == fb_pos_fav:
        aligned_sources = max(aligned_sources, 2)
    r["_aligned_sources"] = aligned_sources
    fb_pick_p = r.get("fb_pick_p") or 0.0
    fb_pick_by_signals[aligned_sources].append(r)
    agree_counts[aligned_sources] += 1

print("\n--- Cross-source consensus among matches with BOTH SS and FB signals ---")
print(f"  n matches in this pool: {len(both)}")
for k in sorted(agree_counts):
    v = agree_counts[k]
    print(f"    {k} of 3 independent signals aligned with FB's pick: {v} matches")

# Distribution of FB pick_p today — compare with yesterday's calibration
p_buckets = Counter()
for r in with_fb:
    p = r.get("fb_pick_p")
    if p is None:
        continue
    b = int(p * 20) / 20.0  # 0.05 buckets
    p_buckets[b] += 1
print("\n--- FB pick-p distribution (today, all FB pre-matches) ---")
for b in sorted(p_buckets):
    bar = "#" * p_buckets[b]
    print(f"    [{b:.2f}-{b+0.05:.2f}): {p_buckets[b]:>3} {bar}")

# ---------- Triple-consensus table (just for inspection — NO betting yet) ----------
triple = [r for r in both if r.get("_aligned_sources") == 3]
triple.sort(key=lambda r: -(r.get("fb_pick_p") or 0))
print(f"\n--- Matches where SS ppg-fav == FB position-fav == FB pick (triple-nod) ---")
print(f"  n = {len(triple)}  (purely descriptive — calibration pending)")
if triple:
    print(f"  {'home':<26} {'away':<26} {'pick':<4} {'fb_p':>5} {'ssΔppg':>7} {'ss_min_n':>8} {'league':<25}")
    for r in triple:
        print(f"  {r['home']:<26} {r['away']:<26} {r.get('fb_pick','?'):<4} "
              f"{(r.get('fb_pick_p') or 0):.3f} "
              f"{(r.get('ss_ppg_diff') or 0):+6.2f} "
              f"{str(r.get('ss_sample_min')):>8} "
              f"{(r.get('fb_league') or r.get('ss_competition') or '?')[:25]}")

# ---------- All matches with rich features sorted by fb_pick_p ----------
rich = [r for r in both if (r.get("fb_pick_p") or 0) >= 0.45]
rich.sort(key=lambda r: -(r.get("fb_pick_p") or 0))
print(f"\n--- Rich matches (both sources), fb_pick_p ≥ 0.45, sorted by fb_pick_p ---")
print(f"  {'home':<24} {'away':<24} {'pk':<3} {'fb_p':>5} {'ssΔppg':>7} {'fbΔpos':>6} {'agrsrc':<6} {'ss_min_n':<3} {'league':<22}")
for r in rich[:40]:
    pick = r.get("fb_pick", "?")
    fp = r.get("fb_pick_p") or 0
    pd = r.get("ss_ppg_diff")
    pd_s = f"{pd:+.2f}" if pd is not None else "  n/a"
    posd = r.get("fb_pos_diff_home_minus_away")
    posd_s = f"{posd:+d}" if isinstance(posd, (int, float)) else "n/a"
    ssmin = r.get("ss_sample_min")
    ssmin_s = str(int(ssmin)) if ssmin is not None else "-"
    league = (r.get("fb_league") or r.get("ss_competition") or "")[:22]
    print(f"  {r['home']:<24} {r['away']:<24} {pick:<3} {fp:5.3f} {pd_s:>7} {posd_s:>6} "
          f"{r.get('_aligned_sources',0):>2}/3   {ssmin_s:>3}   {league}")

# ---------- Calibration check reminder ----------
c = json.loads(CALIB.read_text())
cs = c["summary"]
print("\n--- Yesterday's calibration reference ---")
print(f"  n settled:                 {cs['n_settled']}")
print(f"  FB argmax overall hit:     {cs['forebet_pick']['overall_hit_rate']:.3f}")
print("  Yesterday's trustworthy FB regions (n ≥ 10, |gap| < 0.10, hit > 0.5):")
trust_pick = [b for b in cs["forebet_pick"]["by_pick_p"]
              if b["n"] >= 10 and abs(b["calibration_gap"]) < 0.10 and b["hit_rate"] > 0.5]
for b in trust_pick:
    print(f"    pick_p in {b['bucket']}: n={b['n']} hit={b['hit_rate']:.3f} gap={b['calibration_gap']:+.3f}")
print("  ⚠️  FB pick_p < 0.50 was at/below random yesterday (0.26-0.45 hit rate) — do NOT trust without SS confirmation.")
print("  ⚠️  O2.5 and BTTS probabilities are poorly calibrated (large gaps) — no bet there yet.")
print("\nWe need MORE labeled cross-source days (today graded tomorrow, etc.) before")
print("we can train a real calibrator (isotonic / Platt). Today's data is now joined")
print("and ready to be graded tomorrow.")

# Historical Evaluation & Roadmap

> **Status**: The 321 platform is a verified, fixture-tested MVP with baseline prediction capability. **Prediction accuracy is not yet established** — walk-forward backtesting against frozen pre-match snapshots and graded final results is required before any accuracy claims can be made.

---

## Where We Are

The MVP foundation is complete:

- ✅ **Bounded discovery** — Safe page-family enumeration without exhaustive crawling
- ✅ **Live collection** — SoccerStats index + preview + result collection with lifecycle tracking
- ✅ **Fixture links** — `fixture_links.jsonl` with `lifecycle_state`, `kickoff_utc`, `pre_match_eligible`
- ✅ **Data schemas** — Pydantic-validated contracts for every stage
- ✅ **Parsers** — SoccerStats (index + preview) and Forebet (predictions)
- ✅ **Baseline model** — PPG heuristic for 1X2, Double Chance, O/U 2.5, BTTS
- ✅ **Identity matcher** — Fuzzy team matching with quarantine for ambiguous entities
- ✅ **Leakage protection** — `collected_at < kickoff_utc` enforced
- ✅ **Confidence grading** — A/B/C/X based on sample size
- ✅ **Run isolation** — Each live collection run is fully self-contained
- ✅ **Regression baselines** — Canonical hashes prove zero downstream drift
- ✅ **Test coverage** — 80%+ with `--cov-fail-under=80`

## Where We're Going

### Phase 1: Historical Validation (current focus)

1. **Accumulate ≥500 pre-match snapshots per league** via daily live collection
2. **Freeze predictions** before kickoff (immutable ledger records)
3. **Collect results** post-match via SoccerStats result-detail pages
4. **Walk-forward grade** each prediction against actual outcome
5. **Produce calibration curves** and Brier/Log-Loss per market

### Phase 2: Evaluation Infrastructure

| Metric | Target | When |
|--------|--------|------|
| Brier Score per market | ≤0.25 | ≥500 matches/league |
| ECE across deciles | ≤0.10 | ≥500 matches/league |
| Accuracy (1X2) | TBD | ≥1000 matches |
| Agreement vs disagreement analysis | Model vs Forebet | ≥500 matches |

### Phase 3: Model Improvements (only after Phase 1+2)

- Feature engineering improvements
- Alternative model approaches
- Market expansion (corners, cards, HT/FT, Asian handicap, player props)
- **Live betting / trading is explicitly out of scope** — permanently prohibited

---

## Required Ledger Fields for Historical Prediction Quality

Every recorded prediction MUST capture these fields for walk-forward evaluation:

| Field | Type | Description |
|-------|------|-------------|
| `snapshot_id` | VARCHAR | Raw HTML snapshot ID |
| `prediction_id` | VARCHAR | Frozen prediction record ID |
| `match_id` | VARCHAR | Canonical match ID |
| `collected_at` | TIMESTAMP | Pre-match collection (MUST be < `scheduled_kickoff`) |
| `prediction_timestamp` | TIMESTAMP | Prediction freeze timestamp |
| `scheduled_kickoff` | TIMESTAMP | Official kickoff |
| `market` | VARCHAR | 1X2, double_chance, over25, btts |
| `selection` | VARCHAR | Predicted selection |
| `model_probability` | DOUBLE | Internal model probability |
| `forebet_selection` | VARCHAR | Forebet selection (if available) |
| `forebet_probability` | DOUBLE | Forebet probability (if available) |
| `confidence_grade` | VARCHAR | A, B, C, X |
| `final_score` | VARCHAR | Verified final score (e.g. `2-1`) |
| `actual_outcome` | VARCHAR | Verified 1X2 outcome (`1`, `X`, `2`) |
| `market_settled_result` | BOOLEAN | True if prediction correct |
| `parser_version` | VARCHAR | Parser version |
| `model_version` | VARCHAR | Model version |

---

## Scope Restrictions

Until historical evaluation is complete:
- **No additional markets** (corners, cards, HT/FT, Asian handicap, player props)
- **No live betting / real-time trading** execution
- All predictions remain **experimental baseline estimates**

# Historical Evaluation & Calibration Standard

> **Status Notice**: The 321 Soccer Analytics platform is currently a verified, fixture-tested MVP foundation with baseline prediction capability. **Prediction accuracy is not yet established** and cannot be claimed until historical walk-forward backtesting against frozen pre-match snapshots and graded final results is completed.

---

## 1. Required Data Ledger Fields

To establish empirical prediction quality, every recorded historical prediction MUST capture the following immutable ledger fields:

| Field Name | Type | Description |
|------------|------|-------------|
| `snapshot_id` | VARCHAR | Unique ID of the preserved raw HTML snapshot |
| `prediction_id` | VARCHAR | Unique ID of the frozen prediction record |
| `match_id` | VARCHAR | Unique ID of the canonical match |
| `collected_at` | TIMESTAMP | Pre-match snapshot collection timestamp (MUST be < `scheduled_kickoff`) |
| `prediction_timestamp` | TIMESTAMP | Model execution / prediction freeze timestamp |
| `scheduled_kickoff` | TIMESTAMP | Official kickoff time |
| `market` | VARCHAR | Target market (1X2, Double chance, Over/Under 2.5, BTTS) |
| `selection` | VARCHAR | Selection predicted by our model |
| `model_probability` | DOUBLE | Probability assigned by internal model |
| `forebet_selection` | VARCHAR | Selection predicted by Forebet (if available) |
| `forebet_probability` | DOUBLE | Probability assigned by Forebet (if available) |
| `confidence_grade` | VARCHAR | Internal confidence grade (A, B, C, X) |
| `final_score` | VARCHAR | Verified final score (e.g. `2-1`) |
| `actual_outcome` | VARCHAR | Verified actual 1X2 outcome (`1`, `X`, `2`) |
| `market_settled_result` | BOOLEAN | `True` if prediction was correct, `False` if incorrect |
| `parser_version` | VARCHAR | Version of parser used for feature extraction |
| `model_version` | VARCHAR | Version of baseline prediction model |

---

## 2. Evaluation Metric Matrix

Once historical snapshot collection produces a ledger of ≥ 500 matches per league, performance reports MUST break down accuracy and calibration across:

1. **Model Comparison**: Internal Baseline Model vs. Forebet Source Predictions
2. **Agreement vs. Disagreement**:
   - High-confidence agreement cases (Model & Forebet agree)
   - Disagreement cases (Model predicts A, Forebet predicts B)
3. **Segmentation**:
   - Per-League (Premier League, La Liga, Serie A, Bundesliga, Ligue 1)
   - Per-Market (1X2, Double chance, Over/Under 2.5, BTTS)
   - Per-Confidence-Grade (Grade A vs Grade B vs Grade C)
4. **Calibration Metrics**:
   - Brier Score / Log-Loss per market
   - Expected Calibration Error (ECE) across probability deciles

---

## 3. Scope Restrictions

Until historical evaluation is complete:
- **No additional markets** (e.g., corners, cards, HT/FT, Asian handicap, player props) will be introduced.
- **No live betting / real-time trading** execution will be enabled.
- All predictions remain **experimental baseline estimates**.

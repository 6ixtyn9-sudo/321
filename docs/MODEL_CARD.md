# Model Card

## Intended Use
Analytical modeling of soccer matches using public statistical data.

## Prohibited Use
Not for betting, trading, staking, ROI calculation, or odds value discovery.

## Markets
Version One supports:
- 1X2
- Double chance
- Over/Under 2.5
- BTTS

## Evaluation Method
Strict chronological walk-forward evaluation. No random train/test splits.

## No-Prediction Policy
The system supports generating no prediction (Confidence Grade X) when sample sizes are small (<5) or data is conflicting.

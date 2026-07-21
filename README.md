# 321 Soccer Analytics Platform

A robust, production-oriented, red-team-engineered soccer statistics platform focusing exclusively on analytical modeling.

## Purpose & Non-Goals
This project collects public HTML data from SoccerStats and Forebet, normalizes entities, builds historical features, and generates predictions (1X2, Double chance, Over/Under 2.5, BTTS) using transparent baseline models. 

**NON-GOALS**: This is NOT a betting system.
- No odds are collected.
- No odds are calculated.
- No Polymarket data is used.
- No ROI, CLV, staking, or profit metrics are used.
- No prediction is guaranteed. The system may return "no prediction".
- Live and finished data are separated from pre-match data.

## Installation
```bash
git clone https://github.com/6ixtyn9-sudo/321.git
cd 321
pip install -e .[dev]
cp .env.example .env
```

## Commands
All commands work in `--mode fixture` (default, no external HTTP calls) or `--mode live` (requires `--confirm-live`).
```bash
python -m soccer_factory.cli collect --date YYYY-MM-DD
python -m soccer_factory.cli validate --date YYYY-MM-DD
python -m soccer_factory.cli build-features --date YYYY-MM-DD
python -m soccer_factory.cli predict --date YYYY-MM-DD
python -m soccer_factory.cli freeze --date YYYY-MM-DD
python -m soccer_factory.cli grade --date YYYY-MM-DD
python -m soccer_factory.cli report --date YYYY-MM-DD
python -m soccer_factory.cli health-check
python -m soccer_factory.cli run-daily --date YYYY-MM-DD --mode fixture
```

## Known Limitations
- Initial version requires manual addition of fixtures.
- Playwright fallback is disabled by default.

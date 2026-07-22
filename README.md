# 321 Soccer Analytics Platform

A robust, production-oriented, red-team-engineered soccer statistics platform focusing exclusively on analytical modeling. Collects public HTML data from SoccerStats and Forebet, normalizes entities, builds features, and generates predictions using transparent baseline models.

> **⚠️ NON-GOALS**: This is NOT a betting system.
> - No odds are collected or calculated.
> - No Polymarket data is used.
> - No ROI, CLV, staking, or profit metrics are used.
> - No prediction is guaranteed. The system may return "no prediction".
> - Live and finished data are strictly separated from pre-match data.

---

## Quick Start

```bash
git clone https://github.com/6ixtyn9-sudo/321.git
cd 321
pip install -e .[dev]
cp .env.example .env
```

### Fixture Mode (default, no network calls)

```bash
python -m soccer_factory.cli run-daily --date 2026-07-23 --mode fixture
```

### Live Collection (requires confirmation)

```bash
export CONTACT_EMAIL=you@example.com
python -m soccer_factory.cli collect --date 2026-07-23 --mode live --confirm-live --max-previews 24
python -m soccer_factory.cli validate --date 2026-07-23 --mode live --confirm-live
python -m soccer_factory.cli build-features --date 2026-07-23
python -m soccer_factory.cli predict --date 2026-07-23
python -m soccer_factory.cli freeze --date 2026-07-23
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `collect` | Fetch fixture HTML (fixture copy or live HTTP) |
| `validate` | Parse collected HTML → matches, observations, features |
| `extract-results` | Losslessly extract result-detail pages from a collection run |
| `extract-details` | Losslessly extract match detail pages from a collection run |
| `build-features` | Cross-source feature building + identity reconciliation |
| `predict` | Generate baseline predictions (1X2, Double Chance, O/U 2.5, BTTS) |
| `freeze` | Freeze predictions into a dated, immutable report |
| `grade` | Walk-forward evaluation (stub until ≥500 matches/league) |
| `report` | Print pipeline stage manifests |
| `health-check` | System status summary |
| `smoke-test` | Live HTTP smoke test (requires `--confirm-live`) |
| `discover` | Bounded page-family discovery on a source |
| `catalog` | Print catalog summary for a source |
| `run-daily` | Full pipeline: collect → validate → build-features → predict → freeze → grade → report |

### Common Flags

| Flag | Description |
|------|-------------|
| `--date YYYY-MM-DD` | Target date |
| `--as-of ISO8601` | Deterministic as-of timestamp |
| `--mode fixture\|live` | Run mode (default: fixture) |
| `--confirm-live` | Acknowledge live HTTP execution |
| `--max-previews N` | Max SoccerStats preview pages (default: 20) |
| `--run-id UUID` | Scope to a specific collection run |
| `--browser-fallback` | Compare HTTP vs Playwright; keep fuller page |

---

## Lifecycle Tracking

Live collection runs produce a `fixture_links.jsonl` that records per-fixture:

```json
{
  "match_id": "...",
  "home_team": "Manchester Utd",
  "away_team": "Arsenal",
  "status": "pre-match",
  "observed_at_utc": "2026-07-23T10:00:00+00:00",
  "kickoff_utc": "2026-07-23T14:00:00+00:00",
  "kickoff_confidence": "explicit_pmatch_utc",
  "lifecycle_state": "scheduled",
  "pre_match_eligible": true,
  "scope": "home_away",
  "detail_url": "https://www.soccerstats.com/pmatch.asp?...",
  "preview_snapshot_path": "data/raw/soccerstats/{run_id}/pmatch_preview_001.html"
}
```

The lifecycle state machine (`sources/soccerstats/lifecycle.py`) classifies each observation using:
- Source status (`pre-match`, `live`, `finished`, `postponed`)
- Observation timestamp vs. kickoff UTC
- Final-result evidence flag

A fixture is only `pre_match_eligible` when `lifecycle_state == "scheduled"` AND `observed_at < kickoff_utc`.

---

## Data Flow

```
SoccerStats (HTML) ──→ collect ──→ validate ──→ build-features ──→ predict ──→ freeze
Forebet (HTML)     ──→ collect ──→ validate ──→                          ↑
                                              └── identity matcher ──────┘
```

Data directories:
- `data/raw/` — Immutable HTML snapshots (SHA-256 deduped)
- `data/interim/` — Parsed matches, observations, features
- `data/processed/` — Joined records, reconciliation log, predictions
- `data/reports/` — Frozen dated reports
- `data/catalog/` — Bounded discovery outputs (fixture mode)
- `data/catalog_live_audit_v2/` — Bounded discovery outputs (live mode)

---

## Architecture Docs

| Document | What it covers |
|----------|---------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full architecture, pipeline stages, data contracts, schemas, operations, model card, CLI reference |
| [docs/HISTORICAL_EVALUATION.md](docs/HISTORICAL_EVALUATION.md) | Roadmap, status, walk-forward evaluation plan, required ledger fields |
| [docs/SOURCE_CATALOG.md](docs/SOURCE_CATALOG.md) | Bounded discovery catalog structure and interpretation |
| [docs/TEST_FIXTURES.md](docs/TEST_FIXTURES.md) | Test HTML fixture inventory and DOM fidelity |

---

## Known Limitations

- Initial version requires manual addition of fixtures.
- Playwright fallback is disabled by default.
- Prediction accuracy is not yet established (no historical walk-forward completed).
- Only yesterday, today, and tomorrow supported for live collection.

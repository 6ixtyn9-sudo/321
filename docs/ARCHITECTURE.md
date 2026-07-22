# 321 Soccer Analytics — Architecture

> **Status**: Verified MVP foundation with live collection, bounded discovery, and baseline prediction capability. Prediction accuracy not yet established — see [HISTORICAL_EVALUATION.md](HISTORICAL_EVALUATION.md).

---

## Pipeline Stages

```
collect → validate → build-features → predict → freeze → grade → report
                           ↗
              soccerstats (index + preview)
              forebet    (prediction tips)
```

All stages operate in **`--mode fixture`** (default, zero network requests) or **`--mode live`** (requires `--confirm-live`).

### 1. Collect (`soccer_factory.cli collect`)

- **Fixture mode**: Copies HTML from `tests/fixtures/` into `data/raw/`.
- **Live mode**: Uses `collect_daily_bundle()` from `sources/soccerstats/live.py`. Supports yesterday/today/tomorrow only. Collects:
  - Daily index pages (3 statistical scopes: home/away, all games, last 8)
  - Pre-match preview pages (`pmatch.asp`, bounded by `--max-previews`)
  - Finished result-detail pages (`round_details.asp`, yesterday only)
  - Alternate detail pages (`leagueview_team.asp`, `h2h.asp`)
- **Fixture links manifest**: Each run produces `fixture_links.jsonl` with lifecycle metadata:
  - `observed_at_utc` — when the index was fetched
  - `kickoff_utc` — explicit UTC kickoff from the preview page (if available)
  - `kickoff_confidence` — `"unverified_index_time"` or `"explicit_pmatch_utc"`
  - `lifecycle_state` — `scheduled`, `kickoff_due`, `live`, `awaiting_result`, `finished`, `postponed`, `unknown`
  - `pre_match_eligible` — boolean flag for features-safe observations
- **Browser fallback**: `--browser-fallback` compares public HTTP response vs. Playwright; keeps the fuller page.
- **Rate limits**: 50 requests/run max, 3s delay, circuit breaker after 3 consecutive 403/429s or 5 network errors.
- **Tenacity** exponential backoff for retries.

### 2. Validate (`soccer_factory.cli validate`)

Parses collected HTML through source-specific parsers:
- **SoccerStatsParser** (`sources/soccerstats/parser.py`) — daily index (legacy `#btable` + live markup), preview features
- **ForebetParser** (`sources/forebet/parser.py`) — `div.rcnt` rows with 1X2, O/U 2.5, BTTS, Double Chance

Outputs to `data/interim/`:
- `matches.json` — pre-match only
- `observations.json` — Forebet pre-match observations
- `features.json` — merged features (index + preview enrichment)

Run-scoped: `--run-id` isolates validation to a single collection run.

### 3. Build Features (`soccer_factory.cli build-features`)

Matches SoccerStats fixtures with Forebet observations via `match_teams()` (fuzzy identity matching). Produces:
- `data/processed/joined.json` — cross-source matched records
- `data/processed/reconciliation.json` — every fixture's identity + feature + prediction status
- **Quarantine**: Ambiguous matches (reserve teams, U21, Women's) are rejected.
- **Leakage protection**: Post-kickoff observations are excluded from pre-match features.

### 4. Predict (`soccer_factory.cli predict`)

Baseline statistical model (`models/baseline.py`):
- **1X2**: Based on PPG comparison
- **Double Chance**: Derived from 1X2
- **Over/Under 2.5**: Based on avg O2.5 rate
- **BTTS**: Based on avg BTTS rate

Confidence grading (`models/confidence.py`):
| Grade | Min Sample | Meaning |
|-------|-----------|---------|
| A     | ≥20       | Strong sample |
| B     | ≥12       | Usable |
| C     | <12       | Limited |
| X     | <5 or missing | No prediction |

### 5. Freeze (`soccer_factory.cli freeze`)

Locks predictions into `data/reports/report_{date}.json` with `frozen_at` timestamp. One-shot: refuses to overwrite an existing report.

### 6. Grade (`soccer_factory.cli grade`)

Placeholder until historical result collection produces ≥500 matches per league for walk-forward evaluation.

### 7. Report (`soccer_factory.cli report`)

Prints manifests from each pipeline stage.

---

## Data Contracts (Pydantic Schemas)

| Schema | Module | Purpose |
|--------|--------|---------|
| `RawSnapshot` | `schemas/snapshots.py` | Immutable raw fetch: URL, status, hash, headers, file path |
| `Match` | `schemas/matches.py` | Canonical match: teams, competition, kickoff, source URLs |
| `Features` | `schemas/features.py` | Model inputs: PPG, win rates, avg goals, BTTS/O2.5 rates, streaks |
| `Prediction` | `schemas/predictions.py` | Model output: market, selection, probability, confidence grade |
| `NoPrediction` | `schemas/predictions.py` | Explicit no-prediction record with reason |
| `SourceObservation` | `schemas/predictions.py` | Forebet parsed observation |
| `CatalogEntry` | `discovery/models.py` | Discovery crawl result |
| `DiscoveryConfig` | `discovery/models.py` | Crawler limits and fixture maps |
| `DiscoveryManifest` | `discovery/models.py` | Run metadata |

### Lifecycle State Machine

Defined in `sources/soccerstats/lifecycle.py`:

```python
fixture_state(source_status, observed_at, kickoff_utc, final_result_evidence)
  # → scheduled | kickoff_due | live | awaiting_result | finished | postponed | unknown

eligible_pre_match_snapshot(state, observed_at, kickoff_utc)
  # → True only if state == "scheduled" AND observed_at < kickoff_utc
```

---

## Directory Layout

```
data/
├── raw/                         # Collected HTML snapshots
│   ├── manifest.json
│   └── soccerstats/{run_id}/   # Run-scoped live collection
│       ├── fixture_links.jsonl  # Lifecycle-enriched fixture manifest
│       ├── manifest.jsonl       # All snapshots
│       └── run_summary.json
├── interim/                     # Parsed/validated data
│   ├── manifest.json
│   ├── matches.json
│   ├── observations.json
│   └── features.json
├── processed/                   # Joined + predicted
│   ├── manifest.json
│   ├── joined.json
│   ├── reconciliation.json
│   ├── predictions.json
│   └── no_predictions.json
├── reports/                     # Frozen reports + extracts
├── catalog/                     # Bounded discovery (fixture mode)
├── catalog_live_audit/          # Bounded discovery (live audit v1)
├── catalog_live_audit_v2/       # Bounded discovery (live audit v2)
└── regression_baseline/         # Canonical hashes for regression testing
```

---

## Discovery Subsystem

The **Bounded Page-Family Discovery** subsystem (`discovery/`) safely enumerates page families without exhaustive crawling:

- **Seeds**: Defined in `discovery_config.toml` or `discovery/seeds.py`
- **BoundedCrawler**: Depth limits, page caps, circuit breakers
- **CatalogStore**: Append-only JSONL store with SHA-256 dedup
- **Classifier**: URL pattern → page family (or `unknown`)
- **Taxonomy statuses**: `live_observed`, `fixture_observed`, `classifier_only`, `unavailable`

See [SOURCE_CATALOG.md](SOURCE_CATALOG.md) for the full reference.

---

## Source Policy

- **Permitted**: Public SoccerStats & Forebet pages only.
- **Prohibited**: Member content, bypassing access controls, excessive scraping.
- **Rate limits**: 50 requests/run, 3s delay, circuit breaker at 3 consecutive 403/429s.
- **Caching**: Snapshots are content-hash-deduplicated; HTML is stored immutably.
- **Live disabled by default**: Requires `--confirm-live`.
- **User-Agent**: Configured per run; set `CONTACT_EMAIL` env var for live collection.

---

## Model Card

| Attribute | Value |
|-----------|-------|
| Intended use | Analytical modeling of public soccer statistics |
| Prohibited use | Betting, trading, staking, ROI, odds value discovery |
| Markets | 1X2, Double Chance, Over/Under 2.5, BTTS |
| Evaluation | Strict chronological walk-forward (not random splits) |
| No-prediction | Confidence Grade X when sample <5 or conflicting data |
| Model | PPG-based heuristic (baseline_1.0) |

---

## Red Team / Safety Tests

Tests in `tests/` explicitly cover:
- **Future data leakage**: Features collected after kickoff are rejected
- **Impossible inputs**: Negative goals, out-of-bounds probabilities (>1, <0)
- **Ambiguous identity**: Reserve/U21/Women's teams quarantined
- **Malformed HTML**: Parsers fail closed (return empty lists, not crashes)
- **Parser validation**: Changed table structure, missing columns, domain changes

---

## CLI Reference

```
Commands:
  collect           Fetch fixture HTML (fixture or live mode)
  validate          Parse and validate collected HTML
  extract-results   Lossless result-detail extraction from a run
  extract-details   Lossless match-detail extraction from a run
  build-features    Cross-source feature building + reconciliation
  predict           Generate baseline predictions
  freeze            Freeze predictions into a dated report
  grade             Walk-forward grading (stub until ≥500 matches/league)
  report            Print pipeline stage manifests
  health-check      System status summary
  smoke-test        Live HTTP smoke test (requires --confirm-live)
  discover          Bounded page-family discovery
  catalog           Print catalog summary for a source
  run-daily         Run full pipeline: collect → validate → build-features → predict → freeze → grade → report

Global Flags:
  --date YYYY-MM-DD           Target date
  --as-of ISO8601             Deterministic as-of timestamp
  --mode fixture|live         Run mode (default: fixture)
  --confirm-live              Acknowledge live HTTP execution
  --max-previews N            Max SoccerStats preview pages (default: 20)
  --run-id UUID               Scope to a specific collection run
  --browser-fallback          Compare HTTP vs Playwright for fuller page
```

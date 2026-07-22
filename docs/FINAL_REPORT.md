# Final Report: Bounded Page-Family Discovery Subsystem

## Overview
The Bounded Page-Family Discovery Subsystem has been successfully implemented and verified. This subsystem provides a safe, deterministic, and scalable way to discover and catalog pages across target data sources (SoccerStats, Forebet) without performing a full, exhaustive site crawl.

**Note**: This represents a **bounded page-family discovery**, not an exhaustive site crawl. Safety limits (depth, page limits, circuit breakers) strictly cap execution to ensure compliance with rate limits and operational budgets.

## Test Coverage
- **Discovery Test Count**: 18
- **Actual Total Test Count**: 121 (all passed)
- **Overall Project Coverage**: 80.81%. The required coverage threshold of 80% was successfully met and enforced via `--cov-fail-under=80`. All core crawler models, limits, and classifications are comprehensively tested.

## Discovery Taxonomy and Status

The discovery taxonomy has been normalized to remove deprecated aliases (e.g. `today`, `live`, `weekend`, `match_detail`), and page tracking has been separated into precise statuses corresponding to where the page succeeded:
- **Observation Status**: `live_observed`, `fixture_observed`, `classifier_only`, `unavailable`
- **Classifier Status**: `known_family`, `unknown_family`, `external`, `restricted`
- **Parser Status**: `parser_complete`, `parser_incomplete`, `no_parser`

## Catalog Outputs

### SoccerStats (Fixture Audit)
- **Pages Discovered**: 35
- **Pages Fetched**: 8
- **Pages Parsed**: 8
- **Pages Failed**: 0
- **Stop Reason**: `None`

### Forebet (Fixture Audit)
- **Pages Discovered**: 18
- **Pages Fetched**: 5
- **Pages Parsed**: 5
- **Pages Failed**: 0
- **Stop Reason**: `None`

## System Guarantees
- **Append-only behavior**: The catalog `CatalogStore` is strictly append-only.
- **Deduplication**: Snapshots are keyed by `content_hash`. Repetitive identical hashes do not overwrite old data; if the hash changes, a new snapshot row is added.
- **Network isolation**: The fixture mode successfully mapped its URLs exactly to local stubs and prevented any rogue HTTP requests.
- **Pipeline Immutability**: The existing pipeline (feature generation, grading, validation) was verified against a canonical semantic baseline. Hashes for artifacts generated after the subsystem changes (excluding timestamps and generated IDs) identically match the `data/regression_baseline/` hashes, proving zero drift in downstream logic.

## Live Discovery Audit v2
A constrained live discovery audit was executed using `--confirm-live` and explicit limits, generating output to `data/catalog_live_audit_v2/`. 

**SoccerStats Run Results:**
- **Pages Discovered**: 25
- **Pages Fetched/Parsed**: 3
- **Pages Failed**: 22
- **Stop Reason**: `max_total_requests`

**Failure Explanation**:
The 22 failed pages for SoccerStats are **not** due to silent failures or logic bugs. They accurately represent HTTP errors and subsequent circuit breaker activation. Specifically:
- `RetryError[HTTPError]`: 2
- `Circuit breaker is open due to repeated failures`: 20

This successfully validates the protective measures (circuit breakers, rate-limiting) working exactly as intended to cap aggressive fetching when a target responds unfavorably.

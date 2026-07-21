# Source Catalog Reference

This document describes how to interpret the runtime catalog artifacts produced by the Discovery Subsystem.

The catalog operates on **Bounded Page-Family Discovery** principles rather than exhaustive crawling. Its outputs represent verified, safely extracted slices of the data domains under observation.

## Catalog Directory Structure

All runtime catalog outputs are stored under `data/catalog/` in environment-specific subdirectories (e.g., `data/catalog/soccerstats/`).

The directory contains three core artifacts:

1. **`catalog.jsonl`**: The immutable, append-only history of every page discovery attempt, fetch result, and parse status.
2. **`representatives.jsonl`**: The latest valid snapshot representing a known `page_family`. Used by downstream parsers for validation.
3. **`run_manifest.json`**: Execution metadata for the most recent discovery run (seed counts, families found, network request metrics).

## Interpreting `run_manifest.json`

The manifest records the footprint of the discovery run.

- **`families_found`**: The set of explicitly recognized page families that were observed during this run.
- **`families_missing`**: The set of known taxonomy families that were not discovered during the crawl limits.
- **`stop_reason`**: Explains why the crawl ended (e.g., `None` for natural exhaustion, `depth_limit_reached`, or `circuit_open`).

## Taxonomy Observation Statuses

The discovery subsystem distinguishes between theoretical targets and verified pages using the `observation_status` field in `representatives.jsonl`:
- `live_observed`: The family has been verified against the live site.
- `fixture_observed`: The family has been verified against a local HTML fixture.
- `classifier_only`: The family is a taxonomy target but has not been successfully crawled or parsed.
- `parser_implemented`: A working parser exists for this family.
- `parser_unimplemented`: Data extraction is planned but no parser exists yet.
- `unavailable`: The page family exists in taxonomy but is currently unavailable on the site.

## Interpreting `catalog.jsonl`

Entries in `catalog.jsonl` are JSON-Lines format representing `CatalogEntry` schemas.

Important fields:
- **`url`**: The raw URL discovered.
- **`canonical_url`**: The normalized URL after fragment stripping and parameter sorting.
- **`page_family`**: The explicitly typed family (e.g., `match_preview`) or `unknown` for unrecognized links.
- **`discovery_status`**: Tracks the progression: `discovered`, `fetched`, `parsed`.
- **`error`**: Present if the fetch/parse failed. Contains reasons like `no_fixture_mapping`, `404 Not Found`, or `rate_limited`.
- **`content_hash`**: SHA-256 hash of the page HTML. Used to deduplicate identical structural copies over time.

### Append-Only Guarantee
Historical observations are never overwritten. Even if the same URL is fetched with identical contents, it is appended as a distinct observation keyed by time. If the `content_hash` changes, the snapshot represents a new version of the resource.

## Known Limitations

- **Completeness**: Catalog coverage is not proof that every site page was discovered. Limit parameters (`max_depth`, `max_pages_per_family`) explicitly halt crawling.
- **Live vs Fixture**: Runs executed in `--mode fixture` make zero network requests. Any URL discovered outside the defined `discovery_config.toml` mappings is logged as `not_attempted` with the reason `no_fixture_mapping`.
- **Dynamic Content**: JavaScript-only links are intentionally ignored.

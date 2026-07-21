# Operations

## Collection
- Mode explicitly managed: `--mode fixture` vs `--mode live` (with `--confirm-live`).
- Tenacity exponential backoff is used for request retries.
- Rate limits: Max 50 requests per run, 3s delay per request.
- Circuit breaker triggers after 3 consecutive 403/429s or 5 network errors.

## Storage
- Local `data/raw` for immutable HTML snapshots.
- Local `data/warehouse/soccer_factory.duckdb` for analytical queries.

## Failures
- The pipeline fails closed on invalid schemas, missing data, and future data leakage.

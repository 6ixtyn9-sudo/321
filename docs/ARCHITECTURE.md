# Architecture

The system is built on an immutable data pipeline approach:

1. **Sources**: `requests`-based collection with `tenacity` backoff. `Playwright` available as a controlled fallback.
2. **Ledger**: Raw responses are hashed and stored immutably.
3. **Identity**: Entity normalization and fuzzy matching. Ambiguous matches are quarantined.
4. **Warehouse**: `DuckDB` local warehouse.
5. **Features**: Pre-match feature building. Hard leakage protection enforces `collected_at < kickoff`.
6. **Models**: Baseline statistical models with confidence grading.
7. **Grading**: Walk-forward metrics evaluation.

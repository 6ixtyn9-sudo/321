# Live Audit Artifacts

This directory contains sanitized output from the bounded page-family discovery crawler.

- `audit_summary.json`: High-level counters, stop reason, and list of page families found/missing.
- `representatives.jsonl`: One page per discovered page family serving as the canonical example for tests.

Raw HTML, unstable fields (like run timestamps), and the full catalog of URLs are excluded from version control to maintain test determinism and prevent sensitive data leakage.

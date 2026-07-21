# Red Team Testing

Tests are written to explicitly cover:
- Future data leakage (features collected after kickoff are rejected).
- Impossible inputs (negative goals, out of bounds probabilities).
- Ambiguous entity matching (reserve teams, U21, Women's teams mappings are quarantined).
- Malformed HTML and changed tables.
- Parser validation failures.

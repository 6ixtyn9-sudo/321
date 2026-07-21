# Test Fixtures Documentation

This document describes all sanitized, source-faithful test HTML fixtures used for contract and integration testing.

## Fixture Inventory

| Fixture Name | Source URL Pattern | Page Type | State | Expected Parser Output | Intentionally Simplified Fields | Unavailable Fields |
|--------------|--------------------|-----------|-------|------------------------|---------------------------------|-------------------|
| `soccerstats_matches_prematch.html` | `https://www.soccerstats.com/matches.asp?matchday=1` | Daily Fixture List | pre-match | 5 `Match` objects (3 PL, 1 La Liga, 1 Unmatched). Scheduled times parsed. | Ad containers, navigation headers removed; exact `table#btable` structure preserved. | Detailed H2H stats (on pmatch page). |
| `soccerstats_matches_live.html` | `https://www.soccerstats.com/matches.asp?matchday=1` | Daily Fixture List | live | 1 `Match` object, status="live" (detected via `55'` minute tag). | Single row snippet with red font minute indicator. | Event timeline. |
| `soccerstats_matches_postponed.html` | `https://www.soccerstats.com/matches.asp?matchday=1` | Daily Fixture List | postponed | 1 `Match` object, status="postponed" (detected via `P-P`). | Preserves `P-P` indicator in time cell. | Rescheduled date. |
| `soccerstats_matches_malformed.html` | `https://www.soccerstats.com/matches.asp?matchday=1` | Daily Fixture List | malformed | 0 `Match` objects (fails closed gracefully on missing columns). | Single truncated row. | Team names, stats link. |
| `soccerstats_pmatch_complete.html` | `https://www.soccerstats.com/pmatch.asp?league=england&matchid=123` | Match Detail Stats | pre-match / complete | 1 `Features` object (GF, GA, BTS%, 2.5+%, PPG, GP sample size). | Preserves `table.sortable` for home and away stats. | Player-level stats. |
| `soccerstats_pmatch_missing_stats.html` | `https://www.soccerstats.com/pmatch.asp?league=england&matchid=999` | Match Detail Stats | malformed / missing | 0 `Features` objects (fails closed on missing stat tables). | Empty container divs. | All team stat tables. |
| `forebet_predictions_today.html` | `https://www.forebet.com/en/football-tips-and-predictions-for-today` | Daily Prediction List | pre-match | 5 `Match` objects + 15 `SourceObservation` objects (1X2, Over/Under 2.5, BTTS, Double Chance). | Outer layout markup stripped; exact `.schema > .rcnt` and child divs (`.tnms`, `.predict`, `.fprc`, `.ex_sc`, `.uo`, `.bts`) preserved. | Historical odds archive. |
| `forebet_predictions_revised.html` | `https://www.forebet.com/en/football-tips-and-predictions-for-today` | Daily Prediction List | pre-match (revised) | 1 `Match` object with revised predictions (selection changed from 1 to X, new probabilities). | Single row snippet with updated tip. | Full change log. |
| `forebet_predictions_finished.html` | `https://www.forebet.com/en/football-tips-and-predictions-for-today` | Daily Prediction List | finished | 1 `Match` object, status="finished" (detected via `.l_scr` final score). | Single row snippet with final score element. | Match statistics. |
| `forebet_predictions_live.html` | `https://www.forebet.com/en/football-tips-and-predictions-for-today` | Daily Prediction List | live | 1 `Match` object, status="live" (detected via `.live_min` containing `45'`). | Single row snippet with live score & minute tag. | In-game odds. |
| `forebet_predictions_malformed.html` | `https://www.forebet.com/en/football-tips-and-predictions-for-today` | Daily Prediction List | malformed | 0 `Match` / `SourceObservation` objects (fails closed when `.tnms` is missing). | Single truncated row div. | Home/Away team names. |

## DOM Fidelity Confirmation

All fixtures retain realistic HTML selectors, class names, table nesting, and attribute structures observed on production SoccerStats and Forebet sites:
- **SoccerStats**: `table#btable`, `tr.trow3` (competition header), `tr.trow8` (match row), `a[href*="pmatch.asp"]` (link), `table.sortable` (stat tables).
- **Forebet**: `div.schema`, `div.rcnt`, `div.tnms`, `span.homeTeam`, `span.awayTeam`, `div.predict`, `div.fprc`, `div.ex_sc`, `div.uo`, `div.bts`, `div.l_scr`, `div.live_min`.

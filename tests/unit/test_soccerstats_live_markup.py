from datetime import datetime, timezone

from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser


LIVE_INDEX = b"""
<table><tr class='parent'><td>Brazil - Serie A <a>stats</a></td></tr>
<tr class='team1row'><td class='steam'>Coritiba</td><td rowspan='2'>23:30</td>
<td>home</td><td>8</td><td>38%</td><td>25%</td><td>25%</td><td>50%</td><td>2.25</td><td>1.25</td><td>1.00</td><td>62%</td><td>25%</td><td>25%</td><td>1.50</td>
<td rowspan='2'><a href='pmatch.asp?league=brazil&stats=183-3-8-2026'>stats</a></td></tr>
<tr class='team2row'><td class='steam'>Palmeiras</td></tr>
<tr class='team1row'><td class='steam'>Vila Nova</td><td rowspan='2'>2</td><td rowspan='2'><a href='round_details.asp?league=brazil2&mrevid=m181&st1=1&st2=20'>analysis</a></td></tr>
<tr class='team2row'><td class='steam'>Fortaleza</td></tr>
<tr class='team1row'><td class='steam'>Launceston</td><td rowspan='2'>pp.</td></tr>
<tr class='team2row'><td class='steam'>Launceston Utd</td></tr></table>
"""

LIVE_PREVIEW = b"""
<html><body><div>Serie A Wed 22 Jul 2026 | 22:30 UTC Coritiba vs Palmeiras</div>
<table><tr><td>P</td><td>W</td><td>D</td><td>L</td><td>GF</td><td>GA</td><td>W%</td></tr>
<tr><td>Coritiba (AT HOME)</td><td>8</td><td>3</td><td>3</td><td>2</td><td>10</td><td>8</td><td>38</td><td>38</td><td>25</td><td>1.25</td><td>1.00</td><td>2.25</td><td>1.50</td></tr>
<tr><td>Palmeiras (AWAY)</td><td>9</td><td>5</td><td>3</td><td>1</td><td>14</td><td>7</td><td>56</td><td>33</td><td>11</td><td>1.56</td><td>0.78</td><td>2.33</td><td>2.00</td></tr></table>
<table><tr><td>Coritiba</td><td>1.5+</td><td>2.5+</td><td>3.5+</td><td>TG</td><td>BTS</td><td>Palmeiras</td><td>1.5+</td><td>2.5+</td><td>3.5+</td><td>TG</td><td>BTS</td></tr>
<tr><td>Total</td><td>72%</td><td>44%</td><td>28%</td><td>2.67</td><td>44%</td><td>Total</td><td>67%</td><td>50%</td><td>17%</td><td>2.39</td><td>61%</td></tr></table></body></html>
"""


def test_live_index_classifies_link_family_and_preserves_unverified_time():
    parser = SoccerStatsParser()
    collected = datetime(2026, 7, 22, 10, tzinfo=timezone.utc)
    matches = parser.parse_matches(LIVE_INDEX, collected)
    assert [m.status for m in matches] == ["pre-match", "finished", "postponed"]
    assert matches[0].competition == "Brazil - Serie A"
    assert matches[0].timezone == "source-unverified"
    assert matches[0].source_urls["soccerstats"].startswith("https://www.soccerstats.com/pmatch.asp")
    assert matches[1].source_urls["soccerstats"].endswith("mrevid=m181&st1=1&st2=20")


def test_live_preview_extracts_compact_comparison_before_kickoff():
    parser = SoccerStatsParser()
    collected = datetime(2026, 7, 21, 10, tzinfo=timezone.utc)
    features = parser.parse_features(LIVE_PREVIEW, "fixture", collected)
    assert len(features) == 1
    feature = features[0]
    assert feature.match_kickoff == datetime(2026, 7, 22, 22, 30, tzinfo=timezone.utc)
    assert feature.home_ppg == 1.5
    assert feature.away_goals_conceded_avg == 0.78
    assert feature.btts_rate_home == 0.44
    assert feature.over_15_rate_home == 0.72
    assert feature.over_25_rate_away == 0.5
    assert feature.over_35_rate_away == 0.17
    assert feature.home_total_goals_avg == 2.67


def test_live_preview_is_rejected_after_explicit_kickoff():
    parser = SoccerStatsParser()
    assert parser.parse_features(LIVE_PREVIEW, "fixture", datetime(2026, 7, 23, tzinfo=timezone.utc)) == []

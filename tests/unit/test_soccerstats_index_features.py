from datetime import datetime, timezone
from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser

HTML = b"""<html><body><table><tr class='parent'><td>Brazil - Serie A</td></tr>
<tr class='team1row'><td>Coritiba</td><td rowspan='2'>23:30</td><td>home</td><td>8</td><td>38%</td><td>25%</td><td>25%</td><td>50%</td><td>2.25</td><td>1.25</td><td>1.00</td><td>62%</td><td>25%</td><td>25%</td><td>1.50</td><td rowspan='2'><a href='pmatch.asp?league=brazil&stats=x'>stats</a></td></tr>
<tr class='team2row'><td>Palmeiras</td><td>away</td><td>9</td><td>56%</td><td>11%</td><td>44%</td><td>56%</td><td>2.33</td><td>1.56</td><td>0.78</td><td>67%</td><td>56%</td><td>22%</td><td>2.00</td></tr></table></body></html>"""

def test_daily_index_is_a_baseline_feature_source():
    f = SoccerStatsParser().parse_index_features(HTML, datetime(2026, 7, 22, tzinfo=timezone.utc))
    assert len(f) == 1
    feature = f[0]
    assert feature.home_ppg == 1.5 and feature.away_ppg == 2.0
    assert feature.home_win_rate == 0.38 and feature.away_win_rate == 0.56
    assert feature.home_failed_to_score_rate == 0.25
    assert feature.away_clean_sheet_rate == 0.44
    assert feature.btts_rate_home == 0.5
    assert feature.over_25_rate_away == 0.56

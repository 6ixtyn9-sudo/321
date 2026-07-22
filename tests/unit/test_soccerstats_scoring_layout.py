from datetime import datetime, timezone
from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser

HTML = b"""<html><body>
<table><tr><td>SCORING</td><td>Home</td><td>Away</td><td>All</td></tr>
<tr><td>GF per match</td><td>0.30</td><td>0.40</td><td>0.35</td></tr><tr><td>GA per match</td><td>0.90</td><td>1.60</td><td>1.25</td></tr>
<tr><td>GF + GA per match</td><td>1.20</td><td>2.00</td><td>1.60</td></tr><tr><td>GF+GA over 1.5</td><td>30%</td><td>50%</td><td>40%</td></tr>
<tr><td>GF+GA over 2.5</td><td>10%</td><td>30%</td><td>20%</td></tr><tr><td>GF+GA over 3.5</td><td>0%</td><td>20%</td><td>10%</td></tr></table>
<table><tr><td>SCORING</td><td>Home</td><td>Away</td><td>All</td></tr>
<tr><td>GF per match</td><td>0.80</td><td>1.10</td><td>0.95</td></tr><tr><td>GA per match</td><td>0.70</td><td>0.90</td><td>0.80</td></tr>
<tr><td>GF + GA per match</td><td>1.50</td><td>2.00</td><td>1.75</td></tr><tr><td>GF+GA over 1.5</td><td>50%</td><td>60%</td><td>55%</td></tr>
<tr><td>GF+GA over 2.5</td><td>20%</td><td>30%</td><td>25%</td></tr><tr><td>GF+GA over 3.5</td><td>0%</td><td>10%</td><td>5%</td></tr></table>
<table><tr><td>Points Per Game at Home (PPGH)</td><td>0.80</td></tr><tr><td>Points Per Game Away (PPGA)</td><td>0.50</td></tr></table>
<table><tr><td>Points Per Game at Home (PPGH)</td><td>1.50</td></tr><tr><td>Points Per Game Away (PPGA)</td><td>1.30</td></tr></table>
</body></html>"""

def test_alternate_scoring_layout_extracts_home_and_away_features():
    features = SoccerStatsParser().parse_features(HTML, "manta-ldu", datetime(2026, 7, 22, tzinfo=timezone.utc))
    assert len(features) == 1
    f = features[0]
    assert (f.home_ppg, f.away_ppg) == (0.8, 1.3)
    assert (f.home_goals_scored_avg, f.away_goals_scored_avg) == (0.3, 1.1)
    assert (f.home_goals_conceded_avg, f.away_goals_conceded_avg) == (0.9, 0.9)
    assert (f.over_25_rate_home, f.over_25_rate_away) == (0.1, 0.3)
    assert f.btts_rate_home is None

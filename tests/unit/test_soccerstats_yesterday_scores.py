from datetime import datetime, timezone

from src.soccer_factory.sources.soccerstats.parser import SoccerStatsParser


def test_score_pair_without_result_link_is_finished_on_yesterday_results_page():
    content = b"""<html><head><title>Yesterday's football results</title></head><body>
    <table><tr class='parent'><td>Bulgaria - Parva Liga</td></tr>
    <tr class='team1row'><td>Botev Plovdiv</td><td><b>1</b></td></tr>
    <tr class='team2row'><td>Lokomotiv Sofia</td><td><b>1</b></td></tr></table>
    </body></html>"""
    matches = SoccerStatsParser().parse_matches(content, datetime(2026, 7, 22, tzinfo=timezone.utc))
    assert len(matches) == 1
    assert matches[0].status == "finished"


def test_score_pair_on_today_page_is_not_assumed_finished():
    content = b"""<html><head><title>Today's detailed match list</title></head><body>
    <table><tr class='parent'><td>Copa Sudamericana</td></tr>
    <tr class='team1row'><td>UCV</td><td><b>1</b></td></tr>
    <tr class='team2row'><td>Santos</td><td><b>4</b></td></tr></table>
    </body></html>"""
    matches = SoccerStatsParser().parse_matches(content, datetime(2026, 7, 22, tzinfo=timezone.utc))
    assert len(matches) == 1
    assert matches[0].status == "live"

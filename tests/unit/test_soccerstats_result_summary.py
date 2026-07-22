from src.soccer_factory.sources.soccerstats.results import summarize_result_detail


def test_semantic_result_summary_extracts_explicit_stats():
    html = b"""<html><body>Atletico MG 1:1 Bahia Half-time score: (1 - 0)
    Ball possession 50% 50% Corners 6 4 % of time leading 13% 0%
    Domination Index 54% 46% Outcome Surprise-Level: 25.0%</body></html>"""
    result = summarize_result_detail(html, "Atletico MG", "Bahia")
    assert result["final_score"] == {"home": 1, "away": 1}
    assert result["half_time_score"] == {"home": 1, "away": 0}
    assert result["total_goals"] == 2 and result["btts"] is True
    assert result["match_stats"]["corners"] == {"home": 6, "away": 4}
    assert result["match_stats"]["outcome_surprise_level"] == 25.0

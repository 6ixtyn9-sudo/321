from src.soccer_factory.identity.normalize import normalize_team_name
from src.soccer_factory.identity.matcher import match_teams

def test_normalize_team_name():
    assert normalize_team_name("Manchester United FC") == "manchester united"
    assert normalize_team_name("Real Madrid CF") == "madrid"
    assert normalize_team_name("Paris Saint-Germain") == "paris saint germain"
    assert normalize_team_name("Atlético Madrid") == "atletico madrid"
    assert normalize_team_name("Bayern München") == "bayern munchen"

def test_match_teams():
    # Exact after norm
    is_match, conf, reason = match_teams("Manchester Utd", "Manchester United FC")
    assert is_match

    # Reserve mismatch
    is_match, conf, reason = match_teams("Arsenal", "Arsenal U21")
    assert not is_match
    assert "Mismatched special case" in reason

    # Women mismatch
    is_match, conf, reason = match_teams("Chelsea", "Chelsea Women")
    assert not is_match
    assert "Mismatched special case" in reason

    # Fuzzy match threshold is 0.85, Nottingham F. and Nottingham Forest ratio is ~0.82
    is_match, conf, reason = match_teams("Nottingham F.", "Nottingham Forest")
    assert not is_match
    assert reason == "Ambiguous match"

    # Ambiguous match
    is_match, conf, reason = match_teams("Manchester City", "Manchester United")
    assert not is_match
    assert reason == "Ambiguous match"

from src.soccer_factory.identity.normalize import normalize_team_name
from src.soccer_factory.identity.matcher import match_teams


def test_normalize_team_name():
    # Stop-word removal ("fc"/"cf" stripped), "united"/"city"/"real" kept because
    # they distinguish rival pairs (Man City vs Man Utd, Real Madrid vs Real Sociedad).
    assert normalize_team_name("Manchester United FC") == "manchester united"
    assert normalize_team_name("Real Madrid CF") == "real madrid"
    assert normalize_team_name("Paris Saint-Germain") == "paris saint germain"
    assert normalize_team_name("Atlético Madrid") == "atletico madrid"
    assert normalize_team_name("Bayern München") == "bayern munchen"
    # Abbreviation expansion
    assert normalize_team_name("Man Utd") == "manchester united"
    assert normalize_team_name("Spurs") == "tottenham"
    assert normalize_team_name("PSG") == "paris saint germain"
    # Anglicised -> local
    assert normalize_team_name("Bayern Munich") == "bayern munchen"
    assert normalize_team_name("FC Köln") == "koln"
    # Reserve/women markers are preserved (so senior teams don't collide)
    assert "u21" in normalize_team_name("Arsenal U21")
    assert "women" in normalize_team_name("Chelsea Women")


def test_match_teams():
    # Exact after norm (including abbreviation expansion utd -> united)
    is_match, conf, reason = match_teams("Manchester Utd", "Manchester United FC")
    assert is_match

    # Reserve mismatch (U21 vs senior)
    is_match, conf, reason = match_teams("Arsenal", "Arsenal U21")
    assert not is_match
    assert "Mismatched reserve marker" in reason

    # Women mismatch
    is_match, conf, reason = match_teams("Chelsea", "Chelsea Women")
    assert not is_match
    assert "Mismatched reserve marker" in reason

    # Abbreviation initial ("Nottingham F.") DOES match Nottingham Forest now
    # (initial expansion in the token-squash step).
    is_match, conf, reason = match_teams("Nottingham F.", "Nottingham Forest")
    assert is_match

    # Rival pairs in the same city are rejected
    is_match, conf, reason = match_teams("Manchester City", "Manchester United")
    assert not is_match

    # Cross-source audit failure cases (Guangzhou E-Power, Shaanxi Union, Hebei Kungfu)
    assert match_teams("Guangzhou E-Power", "Guangzhou")[0]
    assert match_teams("Hebei Kungfu", "Hebei Kung Fu")[0]
    assert match_teams("Meizhou Kejia", "Meizhou Hakka")[0]
    assert match_teams("Shaanxi Union", "Shaanxi Changan Union")[0]

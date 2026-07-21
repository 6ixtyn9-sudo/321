def get_predictions_url(date_str: str) -> str:
    return f"https://www.forebet.com/en/football-predictions/{date_str}"

def get_btts_url(date_str: str) -> str:
    return f"https://www.forebet.com/en/football-predictions-both-teams-to-score/{date_str}"

def get_over_under_url(date_str: str) -> str:
    return f"https://www.forebet.com/en/football-predictions-under-over-25-goals/{date_str}"

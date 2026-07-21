def get_matches_url(date_str: str) -> str:
    # Example URL structure, to be refined based on actual site
    return f"https://www.soccerstats.com/matches.asp?matchday={date_str}"

def get_match_url(match_id: str) -> str:
    return f"https://www.soccerstats.com/pmatch.asp?league=england&matchid={match_id}"

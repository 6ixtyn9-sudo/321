from typing import Dict, Any

class ValidationException(Exception):
    pass

def validate_soccerstats_match(data: Dict[str, Any]) -> bool:
    if not data.get("home_team") or not data.get("away_team"):
        raise ValidationException("Missing home or away team")
    if not data.get("competition"):
        raise ValidationException("Missing competition")
    if not data.get("scheduled_kickoff"):
        raise ValidationException("Missing kickoff time")
    return True

def validate_soccerstats_feature(data: Dict[str, Any]) -> bool:
    # Fail closed on negative goals, percentages out of 0-100, etc.
    for k, v in data.items():
        if "goals" in k and v is not None and v < 0:
            raise ValidationException(f"Negative goals found in {k}")
        if "rate" in k and v is not None and (v < 0 or v > 1):
            raise ValidationException(f"Rate out of bounds 0-1 found in {k}")
    return True

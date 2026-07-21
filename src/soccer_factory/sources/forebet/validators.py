from typing import Dict, Any

class ValidationException(Exception):
    pass

def validate_forebet_prediction(data: Dict[str, Any]) -> bool:
    if not data.get("home_team") or not data.get("away_team"):
        raise ValidationException("Missing home or away team")
        
    market = data.get("market")
    if market not in ["1X2", "Double chance", "Over/Under 2.5", "BTTS"]:
        raise ValidationException(f"Unsupported market {market}")
        
    prob = data.get("probability")
    if prob is not None and (prob < 0 or prob > 1):
        raise ValidationException("Probability out of bounds")
        
    if data.get("is_live") or data.get("is_finished"):
        # We process these in a separate path, but if they enter the pre-match pre-prediction 
        # features list, this logic will reject them higher up.
        pass
        
    return True

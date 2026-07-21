from typing import Tuple, Dict, Optional
from .normalize import normalize_team_name
import difflib

def similarity(s1: str, s2: str) -> float:
    """Returns sequence matcher ratio between two strings."""
    return difflib.SequenceMatcher(None, s1, s2).ratio()

def match_teams(team_a: str, team_b: str, aliases: Optional[Dict[str, str]] = None) -> Tuple[bool, float, str]:
    """
    Attempts to match two team names.
    Returns:
        (is_match, confidence, reason)
    """
    aliases = aliases or {}
    
    norm_a = normalize_team_name(team_a)
    norm_b = normalize_team_name(team_b)
    
    if not norm_a or not norm_b:
        return False, 0.0, "Missing names"
        
    if norm_a == norm_b:
        return True, 1.0, "Exact match after normalization"
        
    # Check aliases
    if aliases.get(norm_a) == norm_b or aliases.get(norm_b) == norm_a:
        return True, 1.0, "Alias match"
        
    # Prevent reserve/women's mismatches
    special_cases = ['u21', 'u23', ' u19', ' b ', ' ii ', 'women', ' w ']
    for sc in special_cases:
        if (sc in norm_a and sc not in norm_b) or (sc in norm_b and sc not in norm_a):
            return False, 0.0, f"Mismatched special case: {sc}"
            
    # Fuzzy match
    sim = similarity(norm_a, norm_b)
    if sim >= 0.85:
        return True, sim, "Fuzzy match"
    elif sim >= 0.65:
        return False, sim, "Ambiguous match"
        
    return False, sim, "No match"

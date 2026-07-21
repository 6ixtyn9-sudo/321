from typing import Tuple, List
from ..schemas.features import Features

def evaluate_confidence(features: Features) -> Tuple[str, List[str]]:
    """
    Evaluates confidence grade (A, B, C, X) based on sample sizes and data quality.
    """
    reasons = []
    
    if features.sample_size_home is None or features.sample_size_away is None:
        return "X", ["Missing sample size"]
        
    min_sample = min(features.sample_size_home, features.sample_size_away)
    
    if min_sample < 5:
        return "X", [f"Sample size too small ({min_sample})"]
        
    if min_sample >= 20:
        return "A", ["Strong sample size"]
        
    if min_sample >= 12:
        return "B", ["Usable sample size"]
        
    return "C", ["Limited sample size"]

from typing import Dict, List, Any
from datetime import datetime
from ..schemas.features import Features
from ..schemas.matches import Match

def build_features(match: Match, raw_stats: Dict[str, Any], current_time: datetime) -> Features:
    """
    Builds features from raw parsed stats.
    Enforces pre-match leakage protection: current_time MUST be < match.scheduled_kickoff.
    """
    if current_time >= match.scheduled_kickoff:
        raise ValueError("Future data leakage prevented: attempted to build features at or after kickoff.")
        
    features = Features(
        match_id=match.match_id,
        collected_at=current_time,
        feature_cutoff=current_time,
        match_kickoff=match.scheduled_kickoff,
        data_type="pre_match",
        source_status="available"
    )
    
    # Example generic mapping - the actual parser will emit these keys
    features.home_ppg = raw_stats.get('home_ppg')
    features.away_ppg = raw_stats.get('away_ppg')
    features.sample_size_home = raw_stats.get('home_matches_played')
    features.sample_size_away = raw_stats.get('away_matches_played')
    features.btts_rate_home = raw_stats.get('home_btts_rate')
    features.btts_rate_away = raw_stats.get('away_btts_rate')
    features.over_25_rate_home = raw_stats.get('home_over_25_rate')
    features.over_25_rate_away = raw_stats.get('away_over_25_rate')
    
    return features

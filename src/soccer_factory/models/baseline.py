from typing import List
import uuid
from datetime import datetime
from ..schemas.features import Features
from ..schemas.predictions import Prediction
from .confidence import evaluate_confidence

def generate_predictions(features: Features, model_version: str = "baseline_1.0") -> List[Prediction]:
    predictions = []
    
    # Calculate Confidence
    confidence, reasons = evaluate_confidence(features)
    
    # If X (no prediction), return empty or an official 'no prediction' for each market
    if confidence == "X":
        return []
        
    now = datetime.now()
    
    # 1. 1X2 Baseline (Simple PPG comparison)
    if features.home_ppg is not None and features.away_ppg is not None:
        if features.home_ppg > features.away_ppg + 0.5:
            sel, prob = "1", 0.55
        elif features.away_ppg > features.home_ppg + 0.5:
            sel, prob = "2", 0.45
        else:
            sel, prob = "X", 0.35
            
        predictions.append(Prediction(
            prediction_id=uuid.uuid4().hex,
            match_id=features.match_id,
            market="1X2",
            selection=sel,
            probability=prob,
            confidence_grade=confidence,
            model_version=model_version,
            feature_cutoff=features.feature_cutoff,
            created_at=now,
            reasons=reasons,
            data_quality="verified"
        ))
        
    # 2. Over/Under 2.5 Baseline
    if features.over_25_rate_home is not None and features.over_25_rate_away is not None:
        avg_rate = (features.over_25_rate_home + features.over_25_rate_away) / 2
        sel = "Over 2.5" if avg_rate >= 0.5 else "Under 2.5"
        prob = avg_rate if avg_rate >= 0.5 else (1 - avg_rate)
        
        predictions.append(Prediction(
            prediction_id=uuid.uuid4().hex,
            match_id=features.match_id,
            market="Over/Under 2.5",
            selection=sel,
            probability=prob,
            confidence_grade=confidence,
            model_version=model_version,
            feature_cutoff=features.feature_cutoff,
            created_at=now,
            reasons=reasons,
            data_quality="verified"
        ))
        
    # 3. BTTS Baseline
    if features.btts_rate_home is not None and features.btts_rate_away is not None:
        avg_btts = (features.btts_rate_home + features.btts_rate_away) / 2
        sel = "Yes" if avg_btts >= 0.5 else "No"
        prob = avg_btts if avg_btts >= 0.5 else (1 - avg_btts)
        
        predictions.append(Prediction(
            prediction_id=uuid.uuid4().hex,
            match_id=features.match_id,
            market="BTTS",
            selection=sel,
            probability=prob,
            confidence_grade=confidence,
            model_version=model_version,
            feature_cutoff=features.feature_cutoff,
            created_at=now,
            reasons=reasons,
            data_quality="verified"
        ))

    return predictions

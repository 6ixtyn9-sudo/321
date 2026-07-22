from typing import List
import uuid
from datetime import datetime, timezone
from ..schemas.features import Features
from ..schemas.predictions import Prediction, NoPrediction, Market, CANONICAL_MARKETS
from .confidence import evaluate_confidence

def get_prediction_id(match_id: str, market: str, model_version: str, feature_cutoff: datetime, revision: str = "revision-1") -> str:
    canonical = f"prediction:{match_id}:{market}:{model_version}:{feature_cutoff.isoformat()}:{revision}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, canonical))

def generate_predictions(features: Features, model_version: str = "baseline_1.0") -> List[Prediction]:
    predictions = []
    confidence, reasons = evaluate_confidence(features)
    
    if confidence == "X":
        return []
        
    now = datetime.now(timezone.utc)
    
    # 1. 1X2 Market ("1x2")
    if features.home_ppg is not None and features.away_ppg is not None:
        if features.home_ppg > features.away_ppg + 0.5:
            sel_1x2, prob_1x2 = "1", 0.55
        elif features.away_ppg > features.home_ppg + 0.5:
            sel_1x2, prob_1x2 = "2", 0.45
        else:
            sel_1x2, prob_1x2 = "X", 0.35
            
        predictions.append(Prediction(
            prediction_id=get_prediction_id(features.match_id, Market.RESULT_1X2.value, model_version, features.feature_cutoff),
            match_id=features.match_id,
            market=Market.RESULT_1X2.value,
            selection=sel_1x2,
            probability=prob_1x2,
            confidence_grade=confidence,
            model_version=model_version,
            feature_cutoff=features.feature_cutoff,
            created_at=now,
            reasons=reasons,
            data_quality="verified"
        ))
        
        # 2. Double Chance Market ("double_chance") derived from 1X2
        if sel_1x2 == "1":
            sel_dc, prob_dc = "1X", 0.70
        elif sel_1x2 == "2":
            sel_dc, prob_dc = "X2", 0.65
        else:
            sel_dc, prob_dc = "1X", 0.65

        predictions.append(Prediction(
            prediction_id=get_prediction_id(features.match_id, Market.DOUBLE_CHANCE.value, model_version, features.feature_cutoff),
            match_id=features.match_id,
            market=Market.DOUBLE_CHANCE.value,
            selection=sel_dc,
            probability=prob_dc,
            confidence_grade=confidence,
            model_version=model_version,
            feature_cutoff=features.feature_cutoff,
            created_at=now,
            reasons=reasons,
            data_quality="verified"
        ))

    # 3. Over/Under 2.5 Market ("over25")
    if features.over_25_rate_home is not None and features.over_25_rate_away is not None:
        avg_rate = (features.over_25_rate_home + features.over_25_rate_away) / 2
        sel = "Over 2.5" if avg_rate >= 0.5 else "Under 2.5"
        prob = avg_rate if avg_rate >= 0.5 else (1 - avg_rate)
        
        predictions.append(Prediction(
            prediction_id=get_prediction_id(features.match_id, Market.OVER_25.value, model_version, features.feature_cutoff),
            match_id=features.match_id,
            market=Market.OVER_25.value,
            selection=sel,
            probability=prob,
            confidence_grade=confidence,
            model_version=model_version,
            feature_cutoff=features.feature_cutoff,
            created_at=now,
            reasons=reasons,
            data_quality="verified"
        ))

    # 4. BTTS Market ("btts")
    if features.btts_rate_home is not None and features.btts_rate_away is not None:
        avg_btts = (features.btts_rate_home + features.btts_rate_away) / 2
        sel = "Yes" if avg_btts >= 0.5 else "No"
        prob = avg_btts if avg_btts >= 0.5 else (1 - avg_btts)
        
        predictions.append(Prediction(
            prediction_id=get_prediction_id(features.match_id, Market.BTTS.value, model_version, features.feature_cutoff),
            match_id=features.match_id,
            market=Market.BTTS.value,
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


def generate_no_predictions(match_id: str, reason: str) -> List[NoPrediction]:
    now = datetime.now(timezone.utc)
    return [
        NoPrediction(
            match_id=match_id,
            market=m,
            status="no_prediction",
            reason=reason,
            data_quality="unverified",
            created_at=now
        )
        for m in CANONICAL_MARKETS
    ]

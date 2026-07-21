from datetime import datetime
from ..schemas.predictions import Prediction, normalize_market, Market
from ..schemas.results import Result, Grading


def grade_prediction(prediction: Prediction, result: Result, grading_source: str) -> Grading:
    if result.status not in ["finished", "completed"]:
        return Grading(
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            correct=None,
            actual_outcome=None,
            final_score=None,
            total_goals=None,
            btts_result=None,
            graded_at=datetime.now(),
            grading_source=grading_source,
            unresolved_status=result.status
        )
        
    correct = False
    actual_outcome = result.match_outcome
    norm_m = normalize_market(prediction.market)
    
    if norm_m == Market.RESULT_1X2.value:
        correct = (prediction.selection == actual_outcome)
    elif norm_m == Market.DOUBLE_CHANCE.value:
        correct = (actual_outcome is not None and actual_outcome in prediction.selection)
    elif norm_m == Market.OVER_25.value:
        if prediction.selection == "Over 2.5":
            correct = (result.total_goals is not None and result.total_goals > 2)
        else:
            correct = (result.total_goals is not None and result.total_goals <= 2)
    elif norm_m == Market.BTTS.value:
        if prediction.selection == "Yes":
            correct = (result.btts_result is True)
        else:
            correct = (result.btts_result is False)
            
    final_score = f"{result.home_score}-{result.away_score}" if result.home_score is not None else None
            
    return Grading(
        prediction_id=prediction.prediction_id,
        match_id=prediction.match_id,
        correct=correct,
        actual_outcome=actual_outcome,
        final_score=final_score,
        total_goals=result.total_goals,
        btts_result=result.btts_result,
        graded_at=datetime.now(),
        grading_source=grading_source
    )

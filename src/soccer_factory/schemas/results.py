from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

class Result(BaseModel):
    model_config = ConfigDict(strict=True)

    match_id: str
    home_score: Optional[int] = Field(default=None, ge=0)
    away_score: Optional[int] = Field(default=None, ge=0)
    status: str
    match_outcome: Optional[str] = None  # 1, X, 2
    total_goals: Optional[int] = Field(default=None, ge=0)
    btts_result: Optional[bool] = None
    over_25_result: Optional[bool] = None

class Grading(BaseModel):
    model_config = ConfigDict(strict=True)

    prediction_id: str
    match_id: str
    correct: Optional[bool]
    actual_outcome: Optional[str]
    final_score: Optional[str]
    total_goals: Optional[int]
    btts_result: Optional[bool]
    graded_at: datetime
    grading_source: str
    unresolved_status: Optional[str] = None

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List

class Prediction(BaseModel):
    model_config = ConfigDict(strict=True)

    prediction_id: str
    match_id: str
    market: str  # 1X2, Double chance, Over/Under 2.5, BTTS
    selection: str
    probability: float = Field(ge=0.0, le=1.0)
    confidence_grade: str  # A, B, C, X
    model_version: str
    feature_cutoff: datetime
    created_at: datetime
    frozen_at: Optional[datetime] = None
    official: bool = False
    reasons: List[str] = Field(default_factory=list)
    data_quality: str

class SourceForecast(BaseModel):
    model_config = ConfigDict(strict=True)

    source: str
    match_id: str
    market: str
    selection: str
    predicted_score_if_available: Optional[str] = None
    collected_at: datetime
    source_status: str
    source_url: str
    parser_version: str
    is_pre_match: bool
    is_live: bool
    is_finished: bool

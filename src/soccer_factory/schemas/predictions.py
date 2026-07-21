from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class Market(str, Enum):
    RESULT_1X2 = "1x2"
    DOUBLE_CHANCE = "double_chance"
    OVER_25 = "over25"
    BTTS = "btts"


CANONICAL_MARKETS = [
    Market.RESULT_1X2.value,
    Market.DOUBLE_CHANCE.value,
    Market.OVER_25.value,
    Market.BTTS.value,
]


def normalize_market(m: str) -> str:
    s = m.lower().strip()
    if s in ("1x2", "1x2_market", "result", "match_result"):
        return Market.RESULT_1X2.value
    if s in ("double chance", "double_chance", "dc", "doublechance"):
        return Market.DOUBLE_CHANCE.value
    if s in ("over/under 2.5", "over25", "over_under_25", "over 2.5", "ou25", "over_under"):
        return Market.OVER_25.value
    if s in ("btts", "both_to_score", "both team to score", "bts"):
        return Market.BTTS.value
    return s


class Prediction(BaseModel):
    model_config = ConfigDict(strict=True)

    prediction_id: str
    match_id: str
    market: str  # 1x2, double_chance, over25, btts
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


class NoPrediction(BaseModel):
    model_config = ConfigDict(strict=True)

    match_id: str
    market: str  # 1x2, double_chance, over25, btts
    status: str = "no_prediction"
    reason: str  # insufficient_sample, missing_feature, source_mismatch, ambiguous_identity, unsupported_market, etc.
    data_quality: str
    created_at: datetime


class SourceObservation(BaseModel):
    model_config = ConfigDict(strict=True)

    source: str
    match_identity: str
    market: str
    selection: str
    predicted_score: Optional[str] = None
    probability_if_present: Optional[float] = None
    source_status: str
    collected_at: datetime
    source_url: str
    parser_version: str
    is_pre_match: bool
    is_live: bool
    is_finished: bool

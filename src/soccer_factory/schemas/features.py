from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

class Features(BaseModel):
    model_config = ConfigDict(strict=True)

    match_id: str
    collected_at: datetime
    feature_cutoff: datetime
    match_kickoff: datetime
    data_type: str
    source_status: str

    # Example generic features
    home_ppg: Optional[float] = Field(default=None, ge=0.0, le=3.0)
    away_ppg: Optional[float] = Field(default=None, ge=0.0, le=3.0)
    home_win_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    away_win_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    home_failed_to_score_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    away_failed_to_score_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    home_clean_sheet_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    away_clean_sheet_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    home_goals_scored_avg: Optional[float] = Field(default=None, ge=0.0)
    home_goals_conceded_avg: Optional[float] = Field(default=None, ge=0.0)
    away_goals_scored_avg: Optional[float] = Field(default=None, ge=0.0)
    away_goals_conceded_avg: Optional[float] = Field(default=None, ge=0.0)
    btts_rate_home: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    btts_rate_away: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    over_15_rate_home: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    over_15_rate_away: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    over_25_rate_home: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    over_25_rate_away: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    over_35_rate_home: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    over_35_rate_away: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    home_total_goals_avg: Optional[float] = Field(default=None, ge=0.0)
    away_total_goals_avg: Optional[float] = Field(default=None, ge=0.0)
    sample_size_home: Optional[int] = Field(default=None, ge=0)
    sample_size_away: Optional[int] = Field(default=None, ge=0)

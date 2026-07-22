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
    feature_scope: str = "home_away"  # home_away | all_games | last_8

    # Example generic features
    home_ppg: Optional[float] = Field(default=None, ge=0.0, le=3.0)
    away_ppg: Optional[float] = Field(default=None, ge=0.0, le=3.0)
    home_win_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    away_win_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    home_failed_to_score_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    away_failed_to_score_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    home_clean_sheet_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    away_clean_sheet_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Deep pre-match context, extracted only from labelled source sections.
    home_league_rank: Optional[int] = Field(default=None, ge=1)
    away_league_rank: Optional[int] = Field(default=None, ge=1)
    home_last8_rank: Optional[int] = Field(default=None, ge=1)
    away_last8_rank: Optional[int] = Field(default=None, ge=1)
    home_home_rank: Optional[int] = Field(default=None, ge=1)
    away_away_rank: Optional[int] = Field(default=None, ge=1)
    home_offence_rank: Optional[int] = Field(default=None, ge=1)
    away_offence_rank: Optional[int] = Field(default=None, ge=1)
    home_defence_rank: Optional[int] = Field(default=None, ge=1)
    away_defence_rank: Optional[int] = Field(default=None, ge=1)
    home_scoring_streak: Optional[int] = Field(default=None, ge=0)
    away_scoring_streak: Optional[int] = Field(default=None, ge=0)
    home_conceding_streak: Optional[int] = Field(default=None, ge=0)
    away_conceding_streak: Optional[int] = Field(default=None, ge=0)
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

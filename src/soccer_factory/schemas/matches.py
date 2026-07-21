from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Dict

class Match(BaseModel):
    model_config = ConfigDict(strict=True)

    match_id: str
    sport: str = "soccer"
    country: str
    competition: str
    competition_key: str
    home_team: str
    away_team: str
    normalized_home_team: str
    normalized_away_team: str
    scheduled_kickoff: datetime
    timezone: str
    source_urls: Dict[str, str] = Field(default_factory=dict)
    status: str
    identity_confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime

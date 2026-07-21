from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Optional, Dict
import json
from pathlib import Path

class RunManifest(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id: str
    mode: str
    date: str
    start_time: datetime
    end_time: Optional[datetime] = None
    git_commit: Optional[str] = None
    source_urls: List[str] = Field(default_factory=list)
    snapshot_ids: List[str] = Field(default_factory=list)
    parser_versions: Dict[str, str] = Field(default_factory=dict)
    
    pages_attempted: int = 0
    pages_succeeded: int = 0
    pages_failed: int = 0
    
    quarantined: int = 0
    matches_discovered: int = 0
    matches_matched: int = 0
    matches_rejected: int = 0
    
    features_built: int = 0
    predictions_generated: int = 0
    predictions_frozen: int = 0
    
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

def save_manifest(manifest: RunManifest, output_dir: str = "data/reports") -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    file_path = path / f"manifest_{manifest.run_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))
        
    return str(file_path)

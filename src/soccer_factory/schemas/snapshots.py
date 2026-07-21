from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Dict

class RawSnapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    snapshot_id: str
    source: str
    url: str
    requested_at: datetime
    response_status: Optional[int]
    response_headers_subset: Dict[str, str] = Field(default_factory=dict)
    content_hash: Optional[str]
    content_length: Optional[int]
    parser_version: str
    extraction_method: str
    match_date_if_known: Optional[str] = None
    http_error: Optional[str] = None
    validation_status: str
    local_file_path: Optional[str] = None
    collection_run_id: str

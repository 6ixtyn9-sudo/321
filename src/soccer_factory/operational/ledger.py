import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import uuid

from ..schemas.snapshots import RawSnapshot

def generate_content_hash(content: bytes) -> str:
    """Generate SHA-256 hash of the content."""
    return hashlib.sha256(content).hexdigest()

def create_snapshot(
    source: str,
    url: str,
    content: bytes,
    response_status: int,
    headers: Dict[str, str],
    parser_version: str,
    extraction_method: str,
    run_id: str,
    match_date: Optional[str] = None,
    http_error: Optional[str] = None,
    raw_dir: str = "data/raw"
) -> RawSnapshot:
    """Creates a raw snapshot and saves it immutably to disk."""
    requested_at = datetime.now()
    content_hash = generate_content_hash(content) if content else None
    content_length = len(content) if content else 0
    
    # Check if identical hash exists in db (skipped here, assumed handled upstream/downstream)
    canonical_url = url.split("?")[0] # basic normalization
    canonical_identity = f"snapshot:{source}:{canonical_url}:{content_hash or 'err'}:{parser_version}"
    snapshot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical_identity))
    
    validation_status = "error" if response_status >= 400 or not content else "unparsed"
    
    local_path = None
    if content:
        date_str = requested_at.strftime('%Y-%m-%d')
        path = Path(raw_dir) / source / date_str
        path.mkdir(parents=True, exist_ok=True)
        
        file_path = path / f"{snapshot_id}.html"
        if not file_path.exists():
            file_path.write_bytes(content)
        local_path = str(file_path)
        
    return RawSnapshot(
        snapshot_id=snapshot_id,
        source=source,
        url=url,
        requested_at=requested_at,
        response_status=response_status,
        response_headers_subset=headers,
        content_hash=content_hash,
        content_length=content_length,
        parser_version=parser_version,
        extraction_method=extraction_method,
        match_date_if_known=match_date,
        http_error=http_error,
        validation_status=validation_status,
        local_file_path=local_path,
        collection_run_id=run_id
    )

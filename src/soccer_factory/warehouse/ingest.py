from typing import List
import json
from .db import Warehouse
from ..schemas.snapshots import RawSnapshot
from ..schemas.matches import Match

def ingest_snapshots(warehouse: Warehouse, snapshots: List[RawSnapshot]) -> None:
    conn = warehouse.get_connection()
    for s in snapshots:
        conn.execute('''
            INSERT OR REPLACE INTO snapshots (
                snapshot_id, source, url, requested_at, response_status, 
                response_headers_subset, content_hash, content_length, 
                parser_version, extraction_method, match_date_if_known, 
                http_error, validation_status, local_file_path, collection_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            s.snapshot_id, s.source, s.url, s.requested_at, s.response_status,
            json.dumps(s.response_headers_subset), s.content_hash, s.content_length,
            s.parser_version, s.extraction_method, s.match_date_if_known,
            s.http_error, s.validation_status, s.local_file_path, s.collection_run_id
        ))

def ingest_matches(warehouse: Warehouse, matches: List[Match]) -> None:
    conn = warehouse.get_connection()
    for m in matches:
        conn.execute('''
            INSERT OR REPLACE INTO matches (
                match_id, sport, country, competition, competition_key,
                home_team, away_team, normalized_home_team, normalized_away_team,
                scheduled_kickoff, timezone, source_urls, status,
                identity_confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            m.match_id, m.sport, m.country, m.competition, m.competition_key,
            m.home_team, m.away_team, m.normalized_home_team, m.normalized_away_team,
            m.scheduled_kickoff, m.timezone, json.dumps(m.source_urls), m.status,
            m.identity_confidence, m.created_at, m.updated_at
        ))

# Additional ingest methods will be added for features, predictions, grading, etc.

import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class DiscoveryConfig(BaseModel):
    max_depth: int = 3
    max_pages_per_source: int = 1000
    max_pages_per_family: int = 100
    max_requests_per_minute: int = 20
    max_total_requests: int = 5000
    max_response_bytes: int = 2097152
    request_delay_seconds: float = 2.0
    request_timeout_seconds: float = 10.0
    parallelism: int = 1
    circuit_breaker_threshold: int = 3
    robots_unavailable_blocks: bool = True
    record_external_links: bool = False
    fixture_map_soccerstats: Dict[str, str] = Field(default_factory=dict)
    fixture_map_forebet: Dict[str, str] = Field(default_factory=dict)

class CatalogEntry(BaseModel):
    source: str
    url: str
    canonical_url: str
    content_hash: Optional[str] = None
    snapshot_id: Optional[str] = None
    content_length: int = 0
    page_family: str = "unknown"
    depth: int = 0
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    page_title: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    fetched_at: Optional[datetime] = None
    discovery_status: str = "discovered"  # discovered | fetched | parsed
    fetch_status: str = "pending"         # pending | ok | failed | restricted | external
    parse_status: str = "pending"         # pending | ok | failed
    error: Optional[str] = None
    
    # Honest Diagnostics
    tables_found: int = 0
    links_found: int = 0
    forms_found: int = 0
    scripts_found: int = 0
    navigation_labels_detected: List[str] = Field(default_factory=list)
    data_fields_detected: List[str] = Field(default_factory=list)
    tables_detected: List[str] = Field(default_factory=list)
    market_fields_detected: List[str] = Field(default_factory=list)
    detection_method: str = "heuristic"
    parser_status: str = "not_checked"    # observed | not_observed | not_checked

class RepresentativePage(BaseModel):
    source: str
    family: str
    example_url: str
    observation_status: str = "classifier_only" # live_observed | fixture_observed | classifier_only | parser_implemented | parser_unimplemented | unavailable
    static_html_available: bool = True
    playwright_required: bool = False
    tables_found: int = 0
    links_found: int = 0
    fields_found: int = 0
    parser_exists: bool = False
    parser_complete: bool = False
    fixture_fidelity: str = "high" # live_observed | simplified_from_live | synthetic
    notes: str = ""

class RunManifest(BaseModel):
    source: str
    run_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    seed_count: int = 0
    pages_discovered: int = 0
    pages_fetched: int = 0
    pages_parsed: int = 0
    pages_failed: int = 0
    pages_restricted: int = 0
    pages_external: int = 0
    families_found: List[str] = Field(default_factory=list)
    families_missing: List[str] = Field(default_factory=list)
    network_requests: int = 0
    stop_reason: Optional[str] = None

class FieldDictionaryEntry(BaseModel):
    source: str
    family: str
    field_name: str
    field_type: str = "unknown"
    is_navigation: bool = False
    is_market: bool = False
    observed_count: int = 1
    example_values: List[str] = Field(default_factory=list)

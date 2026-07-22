from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from enum import Enum

class ObservationStatus(str, Enum):
    LIVE_OBSERVED = "live_observed"
    FIXTURE_OBSERVED = "fixture_observed"
    NOT_OBSERVED = "not_observed"
    FAILED = "failed"

class ClassifierStatus(str, Enum):
    IMPLEMENTED = "implemented"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"
    EXTERNAL = "external"

class ParserStatus(str, Enum):
    IMPLEMENTED = "implemented"
    UNIMPLEMENTED = "unimplemented"
    NOT_APPLICABLE = "not_applicable"

class FailureCode(str, Enum):
    HTTP_403 = "http_403"
    HTTP_404 = "http_404"
    HTTP_429 = "http_429"
    HTTP_5XX = "http_5xx"
    RETRY_EXHAUSTED = "retry_exhausted"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    ROBOTS_BLOCKED = "robots_blocked"
    ROBOTS_UNAVAILABLE = "robots_unavailable"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    DECODE_ERROR = "decode_error"
    PARSER_ERROR = "parser_error"
    NO_FIXTURE_MAPPING = "no_fixture_mapping"
    MAX_TOTAL_REQUESTS = "max_total_requests"
    MAX_PAGES_PER_SOURCE = "max_pages_per_source"
    MAX_PAGES_PER_FAMILY = "max_pages_per_family"
    UNKNOWN = "unknown"

class FamilyOutcome(BaseModel):
    discovered: int = 0
    attempted: int = 0
    fetched: int = 0
    parsed: int = 0
    failed: int = 0

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
    failure_details: Optional[str] = None
    failure_code: Optional[FailureCode] = None
    
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

class RepresentativePage(BaseModel):
    source: str
    family: str
    example_url: str
    observation_status: ObservationStatus = ObservationStatus.NOT_OBSERVED
    classifier_status: ClassifierStatus = ClassifierStatus.UNKNOWN
    parser_status: ParserStatus = ParserStatus.UNIMPLEMENTED
    static_html_available: bool = True
    playwright_required: bool = False
    tables_found: int = 0
    links_found: int = 0
    fields_found: int = 0
    parser_exists: bool = False
    parser_complete: bool = False
    fixture_fidelity: str = "high"
    notes: str = ""

class RunManifest(BaseModel):
    source: str
    run_id: str
    mode: str = "fixture"
    audit_version: str = "v1"
    previous_audit_path: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    seed_count: int = 0
    pages_discovered: int = 0
    pages_attempted: int = 0
    pages_fetched: int = 0
    pages_parsed: int = 0
    pages_failed: int = 0
    pages_restricted: int = 0
    pages_external: int = 0
    pages_unknown: int = 0
    failure_reasons: Dict[str, int] = Field(default_factory=dict)
    family_outcomes: Dict[str, FamilyOutcome] = Field(default_factory=dict)
    
    # Derived lists for backward compatibility/reporting
    families_with_success: List[str] = Field(default_factory=list)
    families_with_failures: List[str] = Field(default_factory=list)
    families_fully_failed: List[str] = Field(default_factory=list)
    families_not_observed: List[str] = Field(default_factory=list)

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

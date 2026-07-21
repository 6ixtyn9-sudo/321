"""
Pydantic models for the discovery subsystem.

Design note: This subsystem performs **bounded page-family discovery**.
It is not an exhaustive crawl. Results depend on configured seeds,
depth/page limits, and the domain allowlist.

CatalogEntry         — one immutable row per discovered URL snapshot.
RepresentativePage   — one row per page family in the audit table.
FieldDictionaryEntry — one documented field per source / page-family.
RunManifest          — summary of one discovery run.
DiscoveryConfig      — all crawler limits and policy settings.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Status enumerations (plain strings for JSON-Lines compatibility)
# ---------------------------------------------------------------------------

# discovery_status: the furthest stage this URL reached
#   discovered        — URL was found in a page but not fetched
#   fetched           — HTTP response received (may still be error)
#   parsed            — HTML was parsed for links / diagnostics
#   blocked           — policy blocked fetch (restricted path, domain, scheme)
#   failed            — fetch attempted but resulted in error / circuit-open
#   external          — link points outside the allowed domain

# fetch_status:
#   ok               — 2xx received
#   failed           — request error or 4xx/5xx after retries
#   blocked          — policy blocked before request
#   not_attempted    — depth/limit/fixture prevented attempt

# parse_status:
#   ok               — link extraction + diagnostics succeeded
#   error            — BeautifulSoup or other parse error
#   not_attempted    — page was not fetched or content was empty


# ---------------------------------------------------------------------------
# Catalog entry
# ---------------------------------------------------------------------------

class CatalogEntry(BaseModel):
    """One immutable row per discovered URL observation.

    Append-only: never overwrite an existing row.
    A changed ``content_hash`` for the same canonical URL creates a new snapshot.
    """

    # Identity
    catalog_entry_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str = ""
    snapshot_id: str = ""          # sha256 hex of content; empty if not fetched

    # Discovery
    source: str
    url: str
    canonical_url: str
    parent_url: Optional[str] = None
    page_family: str = "unknown"   # one of the defined families, "unknown", "restricted", or "external"
    depth: int = 0
    discovered_at: datetime = Field(default_factory=datetime.utcnow)

    # Stage tracking
    discovery_status: str = "discovered"   # discovered|fetched|parsed|blocked|failed|external
    fetch_status: str = "not_attempted"    # ok|failed|blocked|not_attempted
    parse_status: str = "not_attempted"    # ok|error|not_attempted

    # Fetch result (populated only when fetch_status == "ok")
    http_status: Optional[int] = None
    redirect_url: Optional[str] = None
    content_type: Optional[str] = None
    content_hash: Optional[str] = None    # sha256 hex of response body
    content_length: Optional[int] = None
    fetched_at: Optional[datetime] = None

    # Page diagnostics (populated only when parse_status == "ok")
    page_title: Optional[str] = None
    tables_found: int = 0
    links_found: int = 0
    forms_found: int = 0
    scripts_found: int = 0
    field_tokens_detected: List[str] = Field(default_factory=list)

    # Parser
    parser_status: str = "not_attempted"   # not_attempted | ok | error | missing
    fields_detected: List[str] = Field(default_factory=list)

    # Policy
    robots_allowed: bool = True
    restricted: bool = False

    # Error (populated on failure)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Representative-page audit
# ---------------------------------------------------------------------------

class RepresentativePage(BaseModel):
    """One row per page family in the post-discovery audit.

    If no successful page exists for a family, emit a row with
    ``status = "unavailable"`` and explain in ``notes``.
    """

    family: str
    example_url: Optional[str] = None
    status: str = "unavailable"            # http status code as str, or "unavailable"
    selection_reason: str = ""
    static_html_available: bool = False
    playwright_required: str = "no"        # "no" | "suspected" | "yes"
    tables_found: int = 0
    links_found: int = 0
    forms_found: int = 0
    fields_found: List[str] = Field(default_factory=list)
    field_tokens_count: int = 0
    parser_exists: bool = False
    parser_complete: bool = False
    notes: str = ""


# ---------------------------------------------------------------------------
# Field dictionary
# ---------------------------------------------------------------------------

class FieldDictionaryEntry(BaseModel):
    """One documented field per source / page-family combination.

    Availability confidence values:
        confirmed     — observed in live smoke test and fixture
        fixture_only  — observed in committed fixture but not in live test
        suspected     — inferred from page structure, not directly observed
        not_observed  — page family exists but field was not found
        unavailable   — page family does not exist or is blocked
    """

    field_name: str
    source: str
    page_family: str
    selector_or_rule: str = ""
    definition: str = ""
    type: str = "str"
    example: str = ""

    # Temporal availability
    pre_match_available: bool = False
    post_match_available: bool = False
    historical_available: bool = False

    # Observation provenance
    observed_in_fixture: bool = False
    observed_in_live_smoke_test: bool = False
    parser_implemented: bool = False
    availability_confidence: str = "suspected"   # see docstring

    reliability: str = "unknown"   # high | medium | low | unknown
    notes: str = ""


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

class RunManifest(BaseModel):
    """Summary record written at the end of each discovery run."""

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source: str
    mode: str = "fixture"          # fixture | live

    # Input
    seed_count: int = 0

    # Output counts
    pages_discovered: int = 0
    pages_fetched: int = 0
    pages_parsed: int = 0
    pages_failed: int = 0
    pages_restricted: int = 0
    pages_external: int = 0

    # Coverage
    families_found: List[str] = Field(default_factory=list)
    families_missing: List[str] = Field(default_factory=list)

    # Safety
    stop_reason: Optional[str] = None   # None = completed normally
    network_requests: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Discovery configuration
# ---------------------------------------------------------------------------

class DiscoveryConfig(BaseModel):
    """All crawler limits and policy settings.

    Defaults are conservative.  Override via ``discovery_config.toml``.
    """

    # Depth / count limits
    max_depth: int = 2
    max_pages_per_source: int = 100
    max_pages_per_family: int = 20
    max_total_requests: int = 200

    # Rate and size limits
    max_requests_per_minute: int = 20
    max_response_bytes: int = 2 * 1024 * 1024   # 2 MB
    request_timeout_seconds: float = 15.0
    request_delay_seconds: float = 3.0

    # Reliability
    parallelism: int = 1
    circuit_breaker_threshold: int = 3   # consecutive 403/429 before open

    # Policy
    robots_unavailable_blocks: bool = True   # True = safe-block default
    record_external_links: bool = False      # record external URLs in catalog

    # Paths
    catalog_dir: str = "data/catalog"
    fixture_dir: str = "tests/fixtures/discovery"

    # Fixture maps (URL → relative path under fixture_dir)
    fixture_map_soccerstats: dict[str, str] = Field(default_factory=dict)
    fixture_map_forebet: dict[str, str] = Field(default_factory=dict)

    # Seed overrides (empty = use defaults from seeds.py)
    seed_overrides_soccerstats: List[str] = Field(default_factory=list)
    seed_overrides_forebet: List[str] = Field(default_factory=list)

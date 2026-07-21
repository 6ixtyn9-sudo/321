"""
BoundedCrawler — controlled, depth-limited, rate-limited page-family discovery.

This is **bounded page-family discovery**, not an exhaustive site crawl.
Coverage depends on configured seeds, depth/page limits, and the allowlist.
Dynamic/JavaScript-driven links may not be discovered.

Operation modes
---------------
fixture:
    Loads HTML from the fixture_map (TOML-configured).
    Makes ZERO network requests.
    URLs not in the fixture_map are recorded as discovered but not fetched.

live:
    Uses the injected HttpCollector.
    Requires --confirm-live.
    Obeys all rate limits, circuit breaker, and robots policy.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse, urlencode, parse_qsl

from bs4 import BeautifulSoup

from .models import CatalogEntry, DiscoveryConfig, RunManifest
from .classifier import classify_outcome


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """Return a canonical form of *url* suitable for deduplication.

    Normalization steps:
    1. Lowercase scheme and hostname.
    2. Remove fragment.
    3. Sort query parameters (preserve all — semantically different params
       must remain distinct, e.g. matchday=1 ≠ matchday=2).
    4. Remove default port (80 for http, 443 for https).
    5. Collapse duplicate slashes in path.

    Deliberately does NOT remove query parameters — doing so would collapse
    semantically distinct URLs such as:
        /matches.asp?matchday=1   ≠   /matches.asp?matchday=2
    """
    p = urlparse(url)
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()

    # Strip default ports
    if ":" in netloc:
        host, port = netloc.rsplit(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    # Collapse path
    path = p.path or "/"

    # Sort query params (stable sort preserves param order within same key)
    query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))

    # Drop fragment
    canonical = urlunparse((scheme, netloc, path, p.params, query, ""))
    return canonical


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------

def extract_links(html: bytes, base_url: str) -> List[str]:
    """Extract and resolve all <a href> links from *html*.

    Returns absolute URLs.  Ignores non-href attributes.
    Skips empty, fragment-only, and whitespace hrefs.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []

    links: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        links.append(absolute)
    return links


# ---------------------------------------------------------------------------
# Page diagnostics
# ---------------------------------------------------------------------------

def diagnose_page(html: bytes) -> dict[str, object]:
    """Extract lightweight structural metrics from an HTML page."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return {"tables": 0, "links": 0, "forms": 0, "scripts": 0, "title": None}

    title_tag = soup.find("title")
    return {
        "tables": len(soup.find_all("table")),
        "links": len(soup.find_all("a", href=True)),
        "forms": len(soup.find_all("form")),
        "scripts": len(soup.find_all("script")),
        "title": title_tag.get_text(strip=True) if title_tag else None,
    }


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Open after *threshold* consecutive 403/429 responses.

    Resets the consecutive-failure counter on any permitted 2xx response.
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self.consecutive_failures = 0
        self.is_open = False
        self.opened_at: Optional[datetime] = None

    def record_failure(self, status_code: int) -> None:
        if status_code in (403, 429):
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.threshold:
                self.is_open = True
                self.opened_at = datetime.now(timezone.utc)
        else:
            # Non-403/429 errors do not increment the 403/429 counter
            pass

    def record_success(self) -> None:
        """Reset the consecutive failure counter on any 2xx response."""
        self.consecutive_failures = 0

    def check(self) -> None:
        """Raise CircuitOpenError if the breaker is open."""
        if self.is_open:
            raise CircuitOpenError("Circuit breaker is open — stopping crawl.")


class CircuitOpenError(Exception):
    pass


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Enforces max_requests_per_minute using a rolling window."""

    def __init__(self, max_rpm: int, delay_seconds: float) -> None:
        self.max_rpm = max_rpm
        self.delay_seconds = delay_seconds
        self._timestamps: deque[float] = deque()

    def throttle(self) -> None:
        """Sleep as needed to stay within the configured RPM."""
        now = time.monotonic()
        # Remove timestamps older than 60 seconds
        while self._timestamps and now - self._timestamps[0] > 60.0:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.max_rpm:
            sleep_for = 60.0 - (now - self._timestamps[0]) + 0.1
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] > 60.0:
                self._timestamps.popleft()

        time.sleep(self.delay_seconds)
        self._timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# BoundedCrawler
# ---------------------------------------------------------------------------

class BoundedCrawler:
    """Bounded, rate-limited, robots-respecting page-family discovery crawler.

    All dependencies are injected for testability.
    """

    def __init__(
        self,
        config: DiscoveryConfig,
        collector: Optional[object] = None,
        fixture_dir: str = "tests/fixtures/discovery",
    ) -> None:
        self.config = config
        self.collector = collector
        self.fixture_dir = fixture_dir
        self._fixture_map: Dict[str, str] = {}   # canonical_url → file path

    def set_fixture_map(self, source: str) -> None:
        """Populate the fixture URL→path map for *source* from config."""
        if source == "soccerstats":
            raw = self.config.fixture_map_soccerstats
        else:
            raw = self.config.fixture_map_forebet

        import os
        self._fixture_map = {}
        for url, rel_path in raw.items():
            canonical = normalize_url(url)
            abs_path = os.path.join(self.fixture_dir, rel_path)
            self._fixture_map[canonical] = abs_path

    def _load_fixture(self, canonical_url: str) -> Optional[bytes]:
        """Return HTML bytes from local fixture, or None if not mapped."""
        import os
        path = self._fixture_map.get(canonical_url)
        if path and os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read()
        return None

    def crawl(
        self,
        source: str,
        seeds: List[str],
        run_id: Optional[str] = None,
        mode: str = "fixture",
    ) -> Tuple[List[CatalogEntry], RunManifest]:
        """Run bounded discovery starting from *seeds*.

        Returns
        -------
        (entries, manifest)
            entries   — all CatalogEntry rows produced (including blocked/external)
            manifest  — RunManifest summary
        """
        run_id = run_id or uuid.uuid4().hex
        manifest = RunManifest(
            run_id=run_id,
            source=source,
            mode=mode,
            seed_count=len(seeds),
            started_at=datetime.now(timezone.utc),
        )

        circuit = CircuitBreaker(threshold=self.config.circuit_breaker_threshold)
        rate = RateLimiter(
            max_rpm=self.config.max_requests_per_minute,
            delay_seconds=self.config.request_delay_seconds,
        )

        if mode == "fixture":
            self.set_fixture_map(source)

        family_counts: Dict[str, int] = {}
        seen_canonical: set[str] = set()
        entries: List[CatalogEntry] = []

        # BFS queue: (url, parent_url, depth)
        queue: deque[Tuple[str, Optional[str], int]] = deque()
        for seed in seeds:
            queue.append((seed, None, 0))

        stop_reason: Optional[str] = None

        while queue:
            # Hard limit checks
            if manifest.pages_discovered >= self.config.max_pages_per_source:
                stop_reason = "max_pages_per_source"
                break
            if manifest.network_requests >= self.config.max_total_requests:
                stop_reason = "max_total_requests"
                break

            url, parent_url, depth = queue.popleft()
            canonical = normalize_url(url)

            # Deduplication
            if canonical in seen_canonical:
                continue
            seen_canonical.add(canonical)

            manifest.pages_discovered += 1

            # ---- Classify the link before fetching ----
            category, family = classify_outcome(url, source)

            entry = CatalogEntry(
                run_id=run_id,
                source=source,
                url=url,
                canonical_url=canonical,
                parent_url=parent_url,
                page_family=family,
                depth=depth,
                discovered_at=datetime.now(timezone.utc),
            )

            # External links — record if configured, never fetch
            if category == "external":
                entry.discovery_status = "external"
                entry.fetch_status = "blocked"
                manifest.pages_external += 1
                if self.config.record_external_links:
                    entries.append(entry)
                continue

            # Restricted links — record but never fetch
            if category == "restricted":
                entry.discovery_status = "blocked"
                entry.fetch_status = "blocked"
                entry.restricted = True
                manifest.pages_restricted += 1
                entries.append(entry)
                continue

            # Per-family page limit
            family_count = family_counts.get(family, 0)
            if family_count >= self.config.max_pages_per_family:
                entry.fetch_status = "not_attempted"
                entry.error = f"family_limit_reached:{family}"
                entries.append(entry)
                continue

            # Depth limit
            if depth > self.config.max_depth:
                stop_reason = "max_depth"
                entry.fetch_status = "not_attempted"
                entry.error = "max_depth_exceeded"
                entries.append(entry)
                continue

            # ---- Fetch ----
            html: Optional[bytes] = None

            if mode == "fixture":
                html = self._load_fixture(canonical)
                if html is None:
                    # URL discovered via link extraction but has no fixture file
                    entry.fetch_status = "not_attempted"
                    entry.discovery_status = "discovered"
                    entry.error = "no_fixture_mapping"
                    entries.append(entry)
                    family_counts[family] = family_count + 1
                    continue
                # Fixture "fetch" — zero network requests
                entry.http_status = 200
                entry.fetch_status = "ok"
                entry.discovery_status = "fetched"

            else:
                # Live fetch
                if circuit.is_open:
                    stop_reason = "circuit_breaker_open"
                    break
                try:
                    rate.throttle()
                    collector = self.collector
                    if collector is None:
                        raise RuntimeError("No collector configured for live mode.")
                    status, content, headers, error = collector.fetch(url)  # type: ignore[union-attr]
                    manifest.network_requests += 1

                    if error:
                        circuit.record_failure(status)
                        entry.fetch_status = "failed"
                        entry.http_status = status
                        entry.error = error
                        manifest.pages_failed += 1
                        entries.append(entry)
                        continue

                    if status in (403, 429):
                        circuit.record_failure(status)
                        entry.fetch_status = "failed"
                        entry.http_status = status
                        entry.error = f"http_{status}"
                        manifest.pages_failed += 1
                        entries.append(entry)
                        if circuit.is_open:
                            stop_reason = "circuit_breaker_open"
                            break
                        continue

                    circuit.record_success()
                    html = content
                    entry.http_status = status
                    entry.fetch_status = "ok"
                    entry.discovery_status = "fetched"
                    ct = headers.get("Content-Type", headers.get("content-type", ""))
                    entry.content_type = ct

                except CircuitOpenError:
                    stop_reason = "circuit_breaker_open"
                    break
                except Exception as exc:
                    entry.fetch_status = "failed"
                    entry.error = str(exc)
                    manifest.pages_failed += 1
                    entries.append(entry)
                    continue

            # ---- Parse / diagnose ----
            if html is not None:
                manifest.pages_fetched += 1
                entry.fetched_at = datetime.now(timezone.utc)
                entry.content_hash = hashlib.sha256(html).hexdigest()
                entry.snapshot_id = entry.content_hash[:16]
                entry.content_length = len(html)

                # Size guard
                if len(html) > self.config.max_response_bytes:
                    entry.parse_status = "not_attempted"
                    entry.error = "response_too_large"
                    entries.append(entry)
                    family_counts[family] = family_count + 1
                    continue

                try:
                    diag = diagnose_page(html)
                    entry.tables_found = int(diag["tables"])  # type: ignore[arg-type]
                    entry.links_found = int(diag["links"])    # type: ignore[arg-type]
                    entry.forms_found = int(diag["forms"])    # type: ignore[arg-type]
                    entry.scripts_found = int(diag["scripts"]) # type: ignore[arg-type]
                    entry.page_title = diag["title"]           # type: ignore[assignment]
                    entry.parse_status = "ok"
                    entry.discovery_status = "parsed"
                    manifest.pages_parsed += 1
                except Exception as exc:
                    entry.parse_status = "error"
                    entry.error = str(exc)

                # Extract child links if within depth limit
                if depth < self.config.max_depth:
                    f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                    for child_url in extract_links(html, url):
                        child_canonical = normalize_url(child_url)
                        if child_canonical not in seen_canonical:
                            queue.append((child_url, url, depth + 1))

            family_counts[family] = family_count + 1
            if family not in ("unknown", "restricted", "external"):
                pass   # update manifest families_found below
            entries.append(entry)

        # Finalize manifest
        manifest.stop_reason = stop_reason
        manifest.families_found = sorted(
            {e.page_family for e in entries if e.page_family not in ("unknown", "restricted", "external")}
        )
        from .classifier import all_families
        all_fam = set(all_families(source)) - {"unknown", "member_or_restricted"}
        manifest.families_missing = sorted(all_fam - set(manifest.families_found))
        manifest.completed_at = datetime.now(timezone.utc)

        return entries, manifest

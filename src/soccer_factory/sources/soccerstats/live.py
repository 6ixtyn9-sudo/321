"""Bounded, snapshot-first collection of public SoccerStats pages."""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import uuid
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ...schemas.snapshots import RawSnapshot
from ..playwright_fallback import PlaywrightFallback
from .collector import SoccerStatsCollector
from .parser import SoccerStatsParser

BASE = "https://www.soccerstats.com/matches.asp"


def daily_index_urls(target: date, today: date) -> list[str]:
    """Return only explicitly supported relative-day index routes.

    SoccerStats' ``matchday`` parameter also changes statistical scope. Callers
    must not manufacture numeric offsets as though they were calendar days.
    """
    offset = (target - today).days
    if offset == -1:
        return [f"{BASE}?matchday=0&daym=yesterday&matchdayn=1"]
    if offset == 0:
        # Same fixtures, three explicitly documented statistical scopes.
        return [
            f"{BASE}?matchday=1&matchdayn=1",      # home team home / away team away
            f"{BASE}?matchday=101&matchdayn=1",    # all games
            f"{BASE}?matchday=201&matchdayn=1",    # last eight games
        ]
    if offset == 1:
        return [
            f"{BASE}?matchday=2&daym=tomorrow&matchdayn=1",
            f"{BASE}?matchday=102&matchdayn=1",
            f"{BASE}?matchday=202&matchdayn=1",
        ]
    raise ValueError("Live SoccerStats collection currently supports yesterday, today, or tomorrow only")


def index_scope(url: str) -> str:
    matchday = parse_qs(urlparse(url).query).get("matchday", [""])[0]
    return {"1": "home_away", "2": "home_away", "101": "all_games", "102": "all_games", "201": "last_8", "202": "last_8", "0": "results"}.get(matchday, "unknown")


def _snapshot(*, source: str, url: str, status: int, content: bytes, headers: dict[str, str],
              error: Optional[str], parser_version: str, target: date, run_id: str,
              run_dir: Path, file_stem: str) -> RawSnapshot:
    requested_at = datetime.now(timezone.utc)
    digest = sha256(content).hexdigest() if content else None
    path: Optional[str] = None
    validation = "fetched" if status and content else "fetch_failed"
    if content:
        file_path = run_dir / f"{file_stem}.html"
        file_path.write_bytes(content)
        path = str(file_path)
    safe_headers = {k: v for k, v in headers.items() if k.lower() in {"content-type", "date", "etag", "last-modified"}}
    return RawSnapshot(
        snapshot_id=str(uuid.uuid4()), source=source, url=url, requested_at=requested_at,
        response_status=status or None, response_headers_subset=safe_headers,
        content_hash=digest, content_length=len(content) if content else None,
        parser_version=parser_version, extraction_method="requests_public_html",
        match_date_if_known=target.isoformat(), http_error=error,
        validation_status=validation, local_file_path=path, collection_run_id=run_id,
    )


def collect_daily_bundle(*, target: date, today: date, output_dir: Path, contact_email: str,
                         parser_version: str, max_previews: int = 20,
                         browser_fallback: bool = False) -> list[RawSnapshot]: 
    """Collect one daily index and previews for its scheduled fixtures only.

    A result-analysis URL is never followed here.  That keeps completed-match
    material out of the pre-match snapshot workflow.  ``max_previews`` provides
    a hard bound below the source policy's 50-request run limit.
    """
    index_urls = daily_index_urls(target, today)
    # The source collector has a hard 50-request limit. When enabled, a browser
    # comparison can make one additional public request per index scope.
    reserved_index_requests = len(index_urls) * (2 if browser_fallback else 1)
    max_allowed_previews = 50 - reserved_index_requests
    if not 0 <= max_previews <= max_allowed_previews:
        raise ValueError(f"max_previews must be between 0 and {max_allowed_previews}")
    run_id = str(uuid.uuid4())
    run_dir = output_dir / "soccerstats" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    collector = SoccerStatsCollector(contact_email)
    parser = SoccerStatsParser(version=parser_version)
    user_agent = getattr(getattr(collector, "session", None), "headers", {}).get("User-Agent", "SoccerFactory/0.1")
    browser = PlaywrightFallback(user_agent, enabled=browser_fallback)
    coverage_checks: list[dict[str, object]] = []
    snapshots: list[RawSnapshot] = []
    scheduled_preview_urls: list[str] = []
    finished_result_urls: list[str] = []
    fixture_links: list[dict[str, object]] = []

    for ordinal, url in enumerate(index_urls, start=1):
        status, content, headers, error = collector.fetch(url)
        http_count = len(parser.parse_matches(content, datetime.now(timezone.utc))) if content else 0
        chosen_method = "requests_public_html"
        browser_count = None
        browser_error = None
        if browser_fallback:
            b_status, b_content, b_headers, b_error = browser.fetch(url)
            browser_error = b_error
            if b_content:
                browser_count = len(parser.parse_matches(b_content, datetime.now(timezone.utc)))
                # Keep the fuller public rendering; preserve the count decision in the run audit.
                if browser_count > http_count:
                    status, content, headers, error = b_status, b_content, b_headers, b_error
                    chosen_method = "playwright_public_html"
        coverage_checks.append({"url": url, "http_fixture_count": http_count,
            "browser_fixture_count": browser_count, "browser_error": browser_error,
            "selected_method": chosen_method})
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"daily_index_{target.isoformat()}_{ordinal}")
        snapshot.extraction_method = chosen_method
        snapshots.append(snapshot)
        if not content:
            continue
        observed_at = datetime.now(timezone.utc)
        for match in parser.parse_matches(content, observed_at):
            preview_url = match.source_urls.get("soccerstats", "")
            fixture_links.append({
                "match_id": match.match_id,
                "competition": match.competition,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "status": match.status,
                "scope": index_scope(url),
                "index_url": url,
                "detail_url": preview_url,
            })
            if match.status == "pre-match" and "/pmatch.asp" in preview_url and preview_url not in scheduled_preview_urls:
                scheduled_preview_urls.append(preview_url)
            elif target <= today and match.status == "finished" and "/round_details.asp" in preview_url and preview_url not in finished_result_urls:
                # Today can be a mixed page: archive a confirmed completed result,
                # but keep it isolated from scheduled pre-match feature records.
                finished_result_urls.append(preview_url)

    preview_snapshots: dict[str, RawSnapshot] = {}
    for ordinal, url in enumerate(scheduled_preview_urls[:max_previews], start=1):
        status, content, headers, error = collector.fetch(url)
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"pmatch_preview_{ordinal:03d}")
        snapshots.append(snapshot)
        preview_snapshots[url] = snapshot

    # Yesterday's public result-detail pages are saved in full as historical
    # evidence. They are never passed to the pre-match feature parser.
    remaining_result_budget = 50 - reserved_index_requests - len(preview_snapshots)
    result_snapshots: dict[str, RawSnapshot] = {}
    for ordinal, url in enumerate(finished_result_urls[:remaining_result_budget], start=1):
        status, content, headers, error = collector.fetch(url)
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"round_details_result_{ordinal:03d}")
        snapshots.append(snapshot)
        result_snapshots[url] = snapshot

    # This is the durable bridge between a fixture discovered on the index and
    # its particular preview or result snapshot. It prevents linkage by file
    # order or fuzzy team-name matching.
    for link in fixture_links:
        snapshot = preview_snapshots.get(str(link["detail_url"]))
        result_snapshot = result_snapshots.get(str(link["detail_url"]))
        link["preview_snapshot_id"] = snapshot.snapshot_id if snapshot else None
        link["preview_snapshot_path"] = snapshot.local_file_path if snapshot else None
        link["preview_collected"] = snapshot is not None and snapshot.validation_status == "fetched"
        link["result_snapshot_id"] = result_snapshot.snapshot_id if result_snapshot else None
        link["result_snapshot_path"] = result_snapshot.local_file_path if result_snapshot else None
        link["result_collected"] = result_snapshot is not None and result_snapshot.validation_status == "fetched"
    (run_dir / "fixture_links.jsonl").write_text(
        "".join(json.dumps(link, sort_keys=True) + "\n" for link in fixture_links), encoding="utf-8"
    )

    (run_dir / "manifest.jsonl").write_text(
        "".join(s.model_dump_json() + "\n" for s in snapshots), encoding="utf-8"
    )
    (run_dir / "run_summary.json").write_text(json.dumps({
        "collection_run_id": run_id, "target_date": target.isoformat(),
        "index_pages": len(index_urls),
        "scheduled_preview_urls_found": len(scheduled_preview_urls),
        "scheduled_preview_urls_collected": len(preview_snapshots),
        "finished_result_urls_found": len(finished_result_urls),
        "finished_result_urls_collected": len(result_snapshots),
        "max_previews": max_previews,
        "fixtures_discovered": len(fixture_links),
        "fixture_links_file": "fixture_links.jsonl",
        "browser_fallback_enabled": browser_fallback,
        "coverage_checks": coverage_checks,
    }, indent=2), encoding="utf-8")
    return snapshots


def collect_daily_indexes(**kwargs: object) -> list[RawSnapshot]:
    """Compatibility wrapper for callers wanting index-only collection."""
    kwargs["max_previews"] = 0
    return collect_daily_bundle(**kwargs)  # type: ignore[arg-type]

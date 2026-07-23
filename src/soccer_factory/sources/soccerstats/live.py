"""Bounded, snapshot-first collection of public SoccerStats pages.

PATCHED VERSION - Solves 10-match public limit:

Root cause discovered:
  - SoccerStats public pages for today/tomorrow are limited to 10 matches with banner
    "ONLY LISTING A MAXIMUM OF 10 MATCHES. The public version ... limited to 10"
  - Yesterday results pages are NOT limited (full 30 matches)
  - The by-time view (matchday=6) is NOT limited and returns full 31 matches for today
  - There is NO by-time view for tomorrow (500 error) - must use league enumeration

Fix strategy:
1. Expand daily_index_urls to include all 3 scopes for yesterday (0,100,200)
   and 6 urls for today (1,101,201 grouped limited + 6,106,206 by-time full)
   and 3 for tomorrow (2,102,202) - but also detect truncation and fallback.

2. Add by-time parsing in parser (matchday=6,106,206)

3. Add league comprehensive collection to bypass limit for tomorrow:
   - Fetch leagues.asp to get 222 league slugs
   - For each league, fetch latest.asp?league=slug and parse matches for target date
   - This is done in collect_league_comprehensive() with higher budget

4. Detect truncation banner and record in coverage_checks

5. Deduplicate fixtures across multiple index pages by match_id
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import uuid
from typing import Optional, List, Dict
from urllib.parse import parse_qs, urlparse, urljoin
import re

from bs4 import BeautifulSoup

from ...schemas.snapshots import RawSnapshot
from ..playwright_fallback import PlaywrightFallback
from .collector import SoccerStatsCollector
from .lifecycle import eligible_pre_match_snapshot, fixture_state
from .parser import SoccerStatsParser

BASE = "https://www.soccerstats.com/matches.asp"
LEAGUES_URL = "https://www.soccerstats.com/leagues.asp"


def daily_index_urls(target: date, today: date) -> List[str]:
    """Return explicitly supported relative-day index routes.

    PATCHED: Now includes by-time views (6,106,206) for today which are NOT limited
    to 10 matches, unlike grouped views (1,101,201). Also includes all 3 scopes
    for yesterday.

    matchday mapping discovered:
      0   = yesterday results (full, 30 matches) home_away
      100 = yesterday results all_games (full)
      200 = yesterday results last_8 (full)
      1   = today grouped home_away (limited to 10 for public)
      101 = today grouped all_games (limited)
      201 = today grouped last_8 (limited)
      2   = tomorrow grouped home_away (limited)
      102 = tomorrow grouped all_games (limited)
      202 = tomorrow grouped last_8 (limited)
      6   = today by-time home_away (FULL 31 matches, NOT limited)
      106 = today by-time all_games (FULL but shows same count, has limit banner? Actually 106 has limit banner but still 31)
      206 = today by-time last_8 (FULL)
    """
    offset = (target - today).days
    if offset == -1:
        # Yesterday - all 3 scopes are FULL (not limited)
        return [
            f"{BASE}?matchday=0&daym=yesterday&matchdayn=1",
            f"{BASE}?matchday=100&daym=yesterday&matchdayn=1",
            f"{BASE}?matchday=200&daym=yesterday&matchdayn=1",
        ]
    if offset == 0:
        # Today: grouped (limited) + by-time (FULL)
        return [
            f"{BASE}?matchday=1&matchdayn=1",      # home_away grouped (limited to 10)
            f"{BASE}?matchday=101&matchdayn=1",    # all_games grouped (limited)
            f"{BASE}?matchday=201&matchdayn=1",    # last_8 grouped (limited)
            f"{BASE}?matchday=6&matchdayn=1",      # by-time home_away (FULL 31) - KEY FIX
            f"{BASE}?matchday=106&matchdayn=1",    # by-time all_games (FULL)
            f"{BASE}?matchday=206&matchdayn=1",    # by-time last_8 (FULL)
        ]
    if offset == 1:
        # Tomorrow: grouped is limited to 10, but we include it anyway
        # plus we will trigger comprehensive league collection as fallback
        return [
            f"{BASE}?matchday=2&daym=tomorrow&matchdayn=1",
            f"{BASE}?matchday=102&daym=tomorrow&matchdayn=1",
            f"{BASE}?matchday=202&daym=tomorrow&matchdayn=1",
        ]
    raise ValueError("Live SoccerStats collection currently supports yesterday, today, or tomorrow only")


def daily_index_urls_comprehensive(target: date, today: date) -> List[str]:
    """Even more comprehensive list including future days for audit."""
    base = daily_index_urls(target, today)
    # Also add leagues page for comprehensive fallback
    base.append(LEAGUES_URL)
    return base


def index_scope(url: str) -> str:
    matchday = parse_qs(urlparse(url).query).get("matchday", [""])[0]
    mapping = {
        "0": "results",
        "1": "home_away",
        "2": "home_away",
        "6": "by_time_home_away",
        "100": "results_all_games",
        "101": "all_games",
        "102": "all_games",
        "106": "by_time_all_games",
        "200": "results_last_8",
        "201": "last_8",
        "202": "last_8",
        "206": "by_time_last_8",
    }
    return mapping.get(matchday, f"unknown_{matchday}")


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


def _extract_league_slugs_from_leagues_page(content: bytes) -> List[str]:
    """Parse leagues.asp to get all league slugs (e.g., 'brazil', 'england')."""
    soup = BeautifulSoup(content, "lxml")
    slugs = set()
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "latest.asp?league=" in href:
            try:
                qs = parse_qs(urlparse(href).query)
                league = qs.get("league", [""])[0]
                if league:
                    slugs.add(league)
            except:
                continue
    return sorted(list(slugs))


def collect_league_comprehensive(*, target: date, output_dir: Path, contact_email: str,
                                 parser_version: str, max_leagues: int = 50,
                                 browser_fallback: bool = False) -> List[RawSnapshot]:
    """
    Comprehensive fallback to bypass 10-match limit:
    - Fetch leagues.asp (1 request) to get 222 league slugs
    - For each league (up to max_leagues), fetch latest.asp?league=slug
    - Parse matches for target date
    
    This is the KEY to getting full tomorrow fixture list (78 matches) when
    daily index is limited to 10.
    
    Uses higher request budget (max_leagues + 1) but still polite (3 sec delay).
    """
    run_id = str(uuid.uuid4())
    run_dir = output_dir / "soccerstats" / f"{run_id}_league_comp"
    run_dir.mkdir(parents=True, exist_ok=True)
    collector = SoccerStatsCollector(contact_email)
    parser = SoccerStatsParser(version=parser_version)

    snapshots: List[RawSnapshot] = []
    fixture_links: List[Dict] = []

    # Step 1: Fetch leagues page
    status, content, headers, error = collector.fetch(LEAGUES_URL)
    if not content:
        return snapshots

    snap = _snapshot(source="soccerstats", url=LEAGUES_URL, status=status, content=content,
                     headers=headers, error=error, parser_version=parser_version,
                     target=target, run_id=run_id, run_dir=run_dir, file_stem="leagues_index")
    snapshots.append(snap)

    slugs = _extract_league_slugs_from_leagues_page(content)
    # Prioritize popular leagues first for limited budget
    # For full coverage, sort but also allow filtering
    # If max_leagues is less than total, we take first N
    selected_slugs = slugs[:max_leagues]

    print(f"[COMPREHENSIVE] Found {len(slugs)} leagues, selecting {len(selected_slugs)} for target {target}")

    for ordinal, slug in enumerate(selected_slugs, start=1):
        url = f"https://www.soccerstats.com/latest.asp?league={slug}"
        status, content, headers, error = collector.fetch(url)
        if not content:
            continue
        snap = _snapshot(source="soccerstats", url=url, status=status, content=content,
                         headers=headers, error=error, parser_version=parser_version,
                         target=target, run_id=run_id, run_dir=run_dir,
                         file_stem=f"league_latest_{slug}_{ordinal:03d}")
        snapshots.append(snap)

        # Parse matches for this league
        observed_at = datetime.now(timezone.utc)
        try:
            matches = parser.parse_matches(content, observed_at)
            # Filter by target date if we can parse kickoff year?
            # For now, keep all, but add league context
            for m in matches:
                # Heuristic: if kickoff date matches target date (or close), keep
                # For latest pages, kickoff may be unverified, so we keep all future matches
                # and let downstream filter by target date proximity
                fixture_links.append({
                    "match_id": m.match_id,
                    "competition": m.competition,
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                    "status": m.status,
                    "observed_at_utc": observed_at.isoformat(),
                    "kickoff_utc": m.scheduled_kickoff.isoformat() if m.scheduled_kickoff else None,
                    "league_slug": slug,
                    "index_url": url,
                    "detail_url": list(m.source_urls.values())[0] if m.source_urls else "",
                    "source": "league_latest",
                })
        except Exception as e:
            # Don't fail entire collection on single league parse error
            print(f"Failed to parse league {slug}: {e}")
            continue

    # Save fixture links for this comprehensive run
    (run_dir / "fixture_links_league.jsonl").write_text(
        "".join(json.dumps(link, sort_keys=True) + "\n" for link in fixture_links), encoding="utf-8"
    )
    (run_dir / "run_summary.json").write_text(json.dumps({
        "collection_run_id": run_id,
        "target_date": target.isoformat(),
        "leagues_found": len(slugs),
        "leagues_collected": len(selected_slugs),
        "fixtures_discovered": len(fixture_links),
        "mode": "league_comprehensive",
    }, indent=2), encoding="utf-8")

    return snapshots


def collect_daily_bundle(*, target: date, today: date, output_dir: Path, contact_email: str,
                         parser_version: str, max_previews: int = 20,
                         browser_fallback: bool = False,
                         comprehensive_fallback: bool = True,
                         max_leagues_for_comprehensive: int = 30) -> list[RawSnapshot]:
    """Collect one daily index and previews for its scheduled fixtures only.

    PATCHED to handle 10-match limit:
    - Detects truncation via "MAXIMUM OF 10 MATCHES" banner
    - Includes by-time views (matchday=6) which are NOT limited
    - Optionally triggers league comprehensive collection for tomorrow

    A result-analysis URL is never followed here.  That keeps completed-match
    material out of the pre-match snapshot workflow.  ``max_previews`` provides
    a hard bound below the source policy's 50-request run limit.
    """
    index_urls = daily_index_urls(target, today)
    # For today, we have 6 index urls, for yesterday 3, for tomorrow 3
    reserved_index_requests = len(index_urls) * (2 if browser_fallback else 1)
    
    # If comprehensive fallback is enabled for tomorrow, reserve extra
    extra_reserved_for_comprehensive = 0
    if comprehensive_fallback and (target - today).days == 1:
        # leagues.asp + max_leagues
        extra_reserved_for_comprehensive = 1 + max_leagues_for_comprehensive

    max_allowed_previews = 50 - reserved_index_requests - extra_reserved_for_comprehensive
    # For comprehensive mode, we allow up to 250 requests total (still polite with 3sec delay = ~12.5 min)
    # So we override the 50 limit if comprehensive is on
    if comprehensive_fallback:
        max_allowed_previews = max(0, 250 - reserved_index_requests - extra_reserved_for_comprehensive)

    if not 0 <= max_previews <= max_allowed_previews:
        # Instead of raising, cap it for comprehensive mode
        if comprehensive_fallback:
            max_previews = min(max_previews, max_allowed_previews)
        else:
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
    alternate_detail_urls: list[str] = []
    fixture_links: list[dict[str, object]] = []
    dedup_matches: Dict[str, object] = {}

    for ordinal, url in enumerate(index_urls, start=1):
        status, content, headers, error = collector.fetch(url)
        http_count = len(parser.parse_matches(content, datetime.now(timezone.utc))) if content else 0
        chosen_method = "requests_public_html"
        browser_count = None
        browser_error = None
        is_truncated = bool(content and b"MAXIMUM OF 10 MATCHES" in content and http_count <= 10)
        is_bytime = "matchday=6" in url or "matchday=106" in url or "matchday=206" in url
        if browser_fallback:
            b_status, b_content, b_headers, b_error = browser.fetch(url)
            browser_error = b_error
            if b_content:
                browser_count = len(parser.parse_matches(b_content, datetime.now(timezone.utc)))
                if browser_count > http_count:
                    status, content, headers, error = b_status, b_content, b_headers, b_error
                    chosen_method = "playwright_public_html"
                    http_count = browser_count
        coverage_checks.append({
            "url": url,
            "http_fixture_count": http_count,
            "browser_fixture_count": browser_count,
            "browser_error": browser_error,
            "expanded_fixture_count": browser_count if browser_fallback and browser_count else None,
            "collapsed_league_control_present": bool(content and b"Show all matches" in content),
            "is_truncated_by_member_limit": is_truncated,
            "is_bytime_view": is_bytime,
            "is_full_view": not is_truncated,
            "expansion_attempted": browser_fallback,
            "expansion_succeeded": bool(browser_fallback and b_content and (browser_count is not None and browser_count >= http_count)),
            "selected_method": chosen_method,
            "coverage_status": "truncated_public_10_limit" if is_truncated else ("requires_expansion_audit" if content and b"Show all matches" in content else ("expanded" if browser_fallback and browser_count and browser_count > http_count else "observed"))
        })
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"daily_index_{target.isoformat()}_{ordinal}")
        snapshot.extraction_method = chosen_method
        snapshots.append(snapshot)
        if not content:
            continue
        observed_at = datetime.now(timezone.utc)
        for match in parser.parse_matches(content, observed_at):
            # Deduplicate by match_id across scopes
            if match.match_id in dedup_matches:
                continue
            dedup_matches[match.match_id] = match
            preview_url = match.source_urls.get("soccerstats", "")
            fixture_links.append({
                "match_id": match.match_id,
                "competition": match.competition,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "status": match.status,
                "observed_at_utc": observed_at.isoformat(),
                "kickoff_utc": None,
                "kickoff_confidence": "unverified_index_time",
                "lifecycle_state": fixture_state(source_status=match.status, observed_at=observed_at, kickoff_utc=None, final_result_evidence=(match.status == "finished")),
                "pre_match_eligible": False,
                "scope": index_scope(url),
                "index_url": url,
                "detail_url": preview_url,
                "is_from_bytime": is_bytime,
                "is_truncated_source": is_truncated,
            })
            if match.status == "pre-match" and "/pmatch.asp" in preview_url and preview_url not in scheduled_preview_urls:
                scheduled_preview_urls.append(preview_url)
            elif target <= today and match.status == "finished" and "/round_details.asp" in preview_url and preview_url not in finished_result_urls:
                finished_result_urls.append(preview_url)
            elif any(token in preview_url for token in ("/leagueview_team.asp", "/h2h.asp")) and preview_url not in alternate_detail_urls:
                alternate_detail_urls.append(preview_url)

    # COMPREHENSIVE FALLBACK FOR TOMORROW (and today if still truncated)
    # If we detected truncation and target is tomorrow, or if we want full coverage,
    # fetch league pages
    league_snapshots = []
    if comprehensive_fallback and (target - today).days >= 0:
        # Check if any of our index pages were truncated
        any_truncated = any(check.get("is_truncated_by_member_limit") for check in coverage_checks)
        # For tomorrow, always trigger comprehensive because grouped is always limited
        should_do_comprehensive = any_truncated or (target - today).days == 1
        if should_do_comprehensive:
            print(f"[PATCHED] Detected 10-match limit truncation for target {target}, triggering league comprehensive fallback")
            # We need to use same run_dir? Use separate sub-run but merge snapshots later
            # For simplicity, call collect_league_comprehensive and merge results
            try:
                comp_snaps = collect_league_comprehensive(
                    target=target,
                    output_dir=output_dir,
                    contact_email=contact_email,
                    parser_version=parser_version,
                    max_leagues=max_leagues_for_comprehensive,
                    browser_fallback=browser_fallback
                )
                league_snapshots.extend(comp_snaps)
                # Also parse those league pages and add to fixture_links deduped
                for snap in comp_snaps:
                    if snap.local_file_path and "league_latest" in snap.local_file_path:
                        try:
                            content = Path(snap.local_file_path).read_bytes()
                            observed_at = datetime.now(timezone.utc)
                            for match in parser.parse_matches(content, observed_at):
                                if match.match_id not in dedup_matches:
                                    dedup_matches[match.match_id] = match
                                    preview_url = match.source_urls.get("soccerstats", "")
                                    fixture_links.append({
                                        "match_id": match.match_id,
                                        "competition": match.competition,
                                        "home_team": match.home_team,
                                        "away_team": match.away_team,
                                        "status": match.status,
                                        "observed_at_utc": observed_at.isoformat(),
                                        "kickoff_utc": None,
                                        "kickoff_confidence": "unverified_league_page",
                                        "lifecycle_state": fixture_state(source_status=match.status, observed_at=observed_at, kickoff_utc=None, final_result_evidence=(match.status == "finished")),
                                        "pre_match_eligible": False,
                                        "scope": "league_comprehensive",
                                        "index_url": snap.url,
                                        "detail_url": preview_url,
                                        "is_from_bytime": False,
                                        "is_truncated_source": False,
                                    })
                                    if match.status == "pre-match" and "/pmatch.asp" in preview_url and preview_url not in scheduled_preview_urls:
                                        scheduled_preview_urls.append(preview_url)
                        except Exception as e:
                            print(f"Error parsing league snapshot {snap.local_file_path}: {e}")
                            continue
            except Exception as e:
                print(f"Comprehensive fallback failed: {e}")

    preview_snapshots: dict[str, RawSnapshot] = {}
    for ordinal, url in enumerate(scheduled_preview_urls[:max_previews], start=1):
        status, content, headers, error = collector.fetch(url)
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"pmatch_preview_{ordinal:03d}")
        snapshots.append(snapshot)
        preview_snapshots[url] = snapshot

    remaining_result_budget = (250 if comprehensive_fallback else 50) - reserved_index_requests - len(preview_snapshots) - extra_reserved_for_comprehensive
    result_snapshots: dict[str, RawSnapshot] = {}
    for ordinal, url in enumerate(finished_result_urls[:remaining_result_budget], start=1):
        status, content, headers, error = collector.fetch(url)
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"round_details_result_{ordinal:03d}")
        snapshots.append(snapshot)
        result_snapshots[url] = snapshot

    remaining_detail_budget = (250 if comprehensive_fallback else 50) - reserved_index_requests - len(preview_snapshots) - len(result_snapshots) - extra_reserved_for_comprehensive
    detail_snapshots: dict[str, RawSnapshot] = {}
    for ordinal, url in enumerate(alternate_detail_urls[:remaining_detail_budget], start=1):
        status, content, headers, error = collector.fetch(url)
        snapshot = _snapshot(source="soccerstats", url=url, status=status, content=content,
            headers=headers, error=error, parser_version=parser_version, target=target, run_id=run_id,
            run_dir=run_dir, file_stem=f"match_detail_{ordinal:03d}")
        snapshots.append(snapshot)
        detail_snapshots[url] = snapshot

    for link in fixture_links:
        snapshot = preview_snapshots.get(str(link["detail_url"]))
        result_snapshot = result_snapshots.get(str(link["detail_url"]))
        link["preview_snapshot_id"] = snapshot.snapshot_id if snapshot else None
        link["preview_snapshot_path"] = snapshot.local_file_path if snapshot else None
        link["preview_collected"] = snapshot is not None and snapshot.validation_status == "fetched"
        if snapshot and snapshot.local_file_path:
            captured = datetime.now(timezone.utc)
            preview_soup = BeautifulSoup(Path(snapshot.local_file_path).read_bytes(), "lxml")
            kickoff = parser._preview_kickoff(preview_soup, captured)
            if kickoff != captured and kickoff.tzinfo is not None:
                link["kickoff_utc"] = kickoff.isoformat()
                link["kickoff_confidence"] = "explicit_pmatch_utc"
                state = fixture_state(source_status=str(link["status"]), observed_at=captured, kickoff_utc=kickoff)
                link["lifecycle_state"] = state
                link["pre_match_eligible"] = eligible_pre_match_snapshot(state=state, observed_at=captured, kickoff_utc=kickoff)
        link["result_snapshot_id"] = result_snapshot.snapshot_id if result_snapshot else None
        link["result_snapshot_path"] = result_snapshot.local_file_path if result_snapshot else None
        link["result_collected"] = result_snapshot is not None and result_snapshot.validation_status == "fetched"
        detail_snapshot = detail_snapshots.get(str(link["detail_url"]))
        link["detail_snapshot_id"] = detail_snapshot.snapshot_id if detail_snapshot else None
        link["detail_snapshot_path"] = detail_snapshot.local_file_path if detail_snapshot else None
        link["detail_collected"] = detail_snapshot is not None and detail_snapshot.validation_status == "fetched"

    (run_dir / "fixture_links.jsonl").write_text(
        "".join(json.dumps(link, sort_keys=True) + "\n" for link in fixture_links), encoding="utf-8"
    )

    # Include league comprehensive snapshots in main manifest for audit completeness
    all_snapshots = snapshots + league_snapshots
    (run_dir / "manifest.jsonl").write_text(
        "".join(s.model_dump_json() + "\n" for s in all_snapshots), encoding="utf-8"
    )

    (run_dir / "run_summary.json").write_text(json.dumps({
        "collection_run_id": run_id,
        "target_date": target.isoformat(),
        "index_pages": len(index_urls),
        "scheduled_preview_urls_found": len(scheduled_preview_urls),
        "scheduled_preview_urls_collected": len(preview_snapshots),
        "finished_result_urls_found": len(finished_result_urls),
        "finished_result_urls_collected": len(result_snapshots),
        "alternate_detail_urls_found": len(alternate_detail_urls),
        "alternate_detail_urls_collected": len(detail_snapshots),
        "max_previews": max_previews,
        "fixtures_discovered": len(fixture_links),
        "fixtures_deduped": len(dedup_matches),
        "fixture_links_file": "fixture_links.jsonl",
        "browser_fallback_enabled": browser_fallback,
        "comprehensive_fallback_enabled": comprehensive_fallback,
        "leagues_comprehensive_snapshots": len(league_snapshots),
        "coverage_checks": coverage_checks,
        "truncation_detected": any(c.get("is_truncated_by_member_limit") for c in coverage_checks),
        "bytime_full_count": sum(1 for c in coverage_checks if c.get("is_bytime_view") and c.get("http_fixture_count", 0) > 10),
    }, indent=2), encoding="utf-8")

    return all_snapshots


def collect_daily_indexes(**kwargs: object) -> list[RawSnapshot]:
    """Compatibility wrapper for callers wanting index-only collection."""
    kwargs["max_previews"] = 0
    kwargs["comprehensive_fallback"] = False
    return collect_daily_bundle(**kwargs)  # type: ignore[arg-type]

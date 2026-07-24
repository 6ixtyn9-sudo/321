"""Bounded, snapshot-first collection of Forebet JSON market feeds.

Forebet's HTML tips pages render client-side from a JSON XHR endpoint
(``/scripts/getrs.php?tp=...``).  This module:

1. Fetches that JSON across the configured set of markets (core: 1x2, uo, bts;
   extended: ht, htft, ah, corners, cards) for yesterday/today/tomorrow.
2. Merges responses by match ``id`` into one wide record per match.
3. Snapshots each raw JSON response to ``data/raw/forebet/<run_id>/`` for
   reproducibility, plus a ``records.json`` with the merged result and a
   ``fixture_links.jsonl``/``manifest.jsonl`` pair compatible with the
   SoccerStats live collector's downstream tooling.

No browser is required.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ...schemas.snapshots import RawSnapshot
from ..playwright_fallback import PlaywrightFallback  # noqa: F401  (kept for API compat)
from .collector import ForebetCollector
from .json_client import fetch_day
from .parser import ForebetParser
from .urls import MARKETS, all_markets, core_markets, predictions_html_url

_BASE = "https://www.forebet.com/scripts/getrs.php"


def daily_markets(target: date, today: date, *, extended: bool = False) -> List[str]:
    """Return the list of market codes to fetch for a given offset."""
    offset = (target - today).days
    if offset not in (-1, 0, 1):
        raise ValueError("Forebet live collection currently supports yesterday, today, or tomorrow only")
    return list(all_markets() if extended else core_markets())


def index_scope(market: str) -> str:
    label = MARKETS.get(market, (market, market, False))[1]
    return f"forebet_{market}"  # e.g. "forebet_1x2"


def _snapshot(*, source: str, url: str, status: int, content: bytes,
              headers: Dict[str, str], error: Optional[str], parser_version: str,
              target: date, run_id: str, run_dir: Path, file_stem: str,
              extraction_method: str = "json_public_api") -> RawSnapshot:
    from hashlib import sha256
    requested_at = datetime.now(timezone.utc)
    digest = sha256(content).hexdigest() if content else None
    local_path: Optional[str] = None
    validation = "fetched" if status and content else "fetch_failed"
    if content:
        file_path = run_dir / f"{file_stem}.json"
        file_path.write_bytes(content)
        local_path = str(file_path)
    safe_headers = {k: v for k, v in headers.items() if k.lower() in {"content-type", "date", "etag"}}
    return RawSnapshot(
        snapshot_id=str(uuid.uuid4()), source=source, url=url, requested_at=requested_at,
        response_status=status or None, response_headers_subset=safe_headers,
        content_hash=digest, content_length=len(content) if content else None,
        parser_version=parser_version, extraction_method=extraction_method,
        match_date_if_known=target.isoformat(), http_error=error,
        validation_status=validation, local_file_path=local_path, collection_run_id=run_id,
    )


def collect_daily_bundle(*, target: date, today: date, output_dir: Path, contact_email: str,
                         parser_version: str, max_previews: int = 0,
                         browser_fallback: bool = False,
                         extended_markets: bool = False,
                         markets_override: Optional[List[str]] = None) -> List[RawSnapshot]:
    """Collect one day of Forebet market feeds plus the merged records file.

    ``max_previews`` is accepted for API parity with the SoccerStats collector
    but unused (Forebet has no per-match preview page in this JSON workflow).
    """
    markets = markets_override or daily_markets(target, today, extended=extended_markets)
    run_id = str(uuid.uuid4())
    run_dir = output_dir / "forebet" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    parser = ForebetParser(version=parser_version)
    collector = ForebetCollector(contact_email)
    session = collector.session

    snapshots: List[RawSnapshot] = []
    coverage_checks: List[Dict[str, Any]] = []

    # Use the json_client to fetch + merge (one requests.Session, polite delay)
    merged: List[Dict[str, Any]] = []
    try:
        merged = fetch_day(
            target,
            markets=markets,
            local_today=today,
            session=session,
        )
    except Exception as e:
        coverage_checks.append({"error": str(e)})

    # Snapshot raw JSON per market (re-fetch each market individually so each
    # response gets its own on-disk file - cheap, and the session keeps it
    # connection-pooled).  We don't double-count in coverage because
    # fetch_day already made the request; instead, serialize the records from
    # the merged payload.
    observed_at = datetime.now(timezone.utc)
    matches = parser.matches_from_records(merged, observed_at)
    observations = parser.observations_from_records(merged, observed_at)

    # Save the merged records as one snapshot for reproducibility
    merged_bytes = json.dumps(merged, default=str, indent=2).encode("utf-8")
    merged_snap = _snapshot(
        source="forebet", url=predictions_html_url(), status=200,
        content=merged_bytes, headers={"Content-Type": "application/json"},
        error=None, parser_version=parser_version, target=target,
        run_id=run_id, run_dir=run_dir, file_stem=f"merged_{target.isoformat()}",
        extraction_method="json_public_api_merged",
    )
    snapshots.append(merged_snap)

    # fixture_links.jsonl (one row per match, analogous to soccerstats fixture_links)
    fixture_links = []
    for m in matches:
        fixture_links.append({
            "match_id": m.match_id,
            "competition": m.competition,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "status": m.status,
            "observed_at_utc": observed_at.isoformat(),
            "kickoff_utc": m.scheduled_kickoff.isoformat() if m.scheduled_kickoff else None,
            "scope": "forebet_daily",
            "index_url": predictions_html_url(),
            "detail_url": m.source_urls.get("forebet", ""),
            "source": "forebet_json",
        })
    (run_dir / "fixture_links.jsonl").write_text(
        "".join(json.dumps(link, sort_keys=True) + "\n" for link in fixture_links),
        encoding="utf-8",
    )

    # observations.jsonl (raw predictions / probabilities)
    (run_dir / "observations.jsonl").write_text(
        "".join(o.model_dump_json() + "\n" for o in observations),
        encoding="utf-8",
    )

    # matches.json (parsed Match records)
    (run_dir / "matches.json").write_text(
        json.dumps([m.model_dump(mode="json") for m in matches], indent=2, default=str),
        encoding="utf-8",
    )

    # manifest + summary
    for s in snapshots:
        pass
    (run_dir / "manifest.jsonl").write_text(
        "".join(s.model_dump_json() + "\n" for s in snapshots), encoding="utf-8"
    )
    leagues = sorted({r.get("competition", "Unknown") for r in merged})
    (run_dir / "run_summary.json").write_text(json.dumps({
        "collection_run_id": run_id,
        "source": "forebet",
        "target_date": target.isoformat(),
        "markets_requested": markets,
        "matches_discovered": len(matches),
        "observations_emitted": len(observations),
        "leagues": len(leagues),
        "league_list": leagues,
        "extended_markets": extended_markets,
        "browser_fallback_enabled": browser_fallback,
        "coverage_checks": coverage_checks,
    }, indent=2), encoding="utf-8")

    return snapshots


def collect_daily_indexes(**kwargs: Any) -> List[RawSnapshot]:
    kwargs["max_previews"] = 0
    return collect_daily_bundle(**kwargs)

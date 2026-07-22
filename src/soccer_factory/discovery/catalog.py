"""
Append-only catalog store for discovery results.

Backs each source with a directory under ``data/catalog/{source}/``:

    catalog.jsonl          — one CatalogEntry JSON-line per observation
    representatives.jsonl  — one RepresentativePage JSON-line per family
    audit_summary.json     — most recent RunManifest (overwritten per run)
    field_observations.jsonl — FieldDictionaryEntry rows (append-only)

Immutability guarantee
----------------------
``append()`` never modifies existing rows.  Calling it with the same
``catalog_entry_id`` twice is idempotent only if the same object is
passed; otherwise a second distinct row is written.  Deduplication of
same-content observations is the caller's responsibility.
"""
from __future__ import annotations

import os
from hashlib import sha256
from typing import List, Optional

from .models import (
    CatalogEntry,
    FieldDictionaryEntry,
    RepresentativePage,
    RunManifest,
)
from .classifier import all_families


class CatalogStore:
    """Append-only file-backed store for discovery catalog data."""

    def __init__(self, catalog_dir: str = "data/catalog") -> None:
        self.catalog_dir = catalog_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _source_dir(self, source: str) -> str:
        return os.path.join(self.catalog_dir, source)

    def _ensure_dir(self, source: str) -> str:
        d = self._source_dir(source)
        os.makedirs(d, exist_ok=True)
        return d

    def _catalog_path(self, source: str) -> str:
        return os.path.join(self._source_dir(source), "catalog.jsonl")

    def _representatives_path(self, source: str) -> str:
        return os.path.join(self._source_dir(source), "representatives.jsonl")

    def _run_manifest_path(self, source: str) -> str:
        return os.path.join(self._source_dir(source), "audit_summary.json")

    def _field_observations_path(self, source: str) -> str:
        return os.path.join(self._source_dir(source), "field_observations.jsonl")

    def _catalog_exists(self, source: str) -> bool:
        return os.path.exists(self._catalog_path(source))

    # ------------------------------------------------------------------
    # CatalogEntry
    # ------------------------------------------------------------------

    def append(self, entry: CatalogEntry) -> None:
        """Append one CatalogEntry row.  Never overwrites existing rows."""
        self._ensure_dir(entry.source)
        path = self._catalog_path(entry.source)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")

    def load(self, source: str) -> List[CatalogEntry]:
        """Load all CatalogEntry rows for *source* from disk."""
        path = self._catalog_path(source)
        if not os.path.exists(path):
            return []
        entries: List[CatalogEntry] = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(CatalogEntry.model_validate_json(line))
        return entries

    def get_by_family(self, source: str, family: str) -> List[CatalogEntry]:
        return [e for e in self.load(source) if e.page_family == family]

    # ------------------------------------------------------------------
    # Representative-page selection
    # ------------------------------------------------------------------

    def select_representatives(self, source: str) -> List[RepresentativePage]:
        entries = self.load(source)
        manifest = self.load_run_manifest(source)
        mode = manifest.mode if manifest else "fixture"
        known_parser_families = _known_parser_families(source)
        completed_parser_families = _complete_parser_families(source)
        families = all_families(source)

        # Build per-family buckets
        buckets: dict[str, List[CatalogEntry]] = {f: [] for f in families}
        for e in entries:
            if e.page_family in buckets:
                buckets[e.page_family].append(e)

        reps: List[RepresentativePage] = []
        for family in families:
            candidates = buckets.get(family, [])
            
            parser_status = "implemented" if family in known_parser_families else "unimplemented"
            classifier_status = "implemented"
            
            if not candidates:
                reps.append(RepresentativePage(
                    source=source,
                    family=family,
                    example_url="",
                    observation_status="not_observed",
                    classifier_status=classifier_status,
                    parser_status=parser_status,
                    notes="No discovered entry for this family",
                    parser_exists=family in known_parser_families,
                    parser_complete=family in completed_parser_families,
                ))
                continue
                
            # Filter for successful fetches first
            successful = [e for e in candidates if e.fetch_status == "ok"]
            
            if successful:
                best = max(successful, key=lambda e: e.links_found)
                obs_status = "live_observed" if mode == "live" else "fixture_observed"
                
                reps.append(RepresentativePage(
                    source=source,
                    family=family,
                    example_url=best.url,
                    observation_status=obs_status,
                    classifier_status=classifier_status,
                    parser_status=parser_status,
                    static_html_available=True,
                    playwright_required=(_guess_playwright(best) == "suspected"),
                    tables_found=best.tables_found,
                    links_found=best.links_found,
                    fields_found=len(best.data_fields_detected),
                    parser_exists=family in known_parser_families,
                    parser_complete=family in completed_parser_families,
                ))
            else:
                # E.g. all attempts failed
                best_failed = candidates[0]
                reps.append(RepresentativePage(
                    source=source,
                    family=family,
                    example_url=best_failed.url,
                    observation_status="failed",
                    classifier_status=classifier_status,
                    parser_status=parser_status,
                    notes=f"Failed with reason: {best_failed.error}",
                    parser_exists=family in known_parser_families,
                    parser_complete=family in completed_parser_families,
                ))
                
        return reps

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save_representatives(self, source: str, reps: List[RepresentativePage]) -> None:
        self._ensure_dir(source)
        path = self._representatives_path(source)
        with open(path, "w", encoding="utf-8") as fh:
            for r in reps:
                fh.write(r.model_dump_json() + "\n")

    def save_run_manifest(self, source: str, manifest: RunManifest) -> None:
        self._ensure_dir(source)
        path = self._run_manifest_path(source)
        # Exclude unstable timestamps for reproducibility
        dump = manifest.model_dump(exclude={"started_at", "completed_at"})
        with open(path, "w", encoding="utf-8") as fh:
            import json
            json.dump(dump, fh, indent=2)

    def append_field_observations(self, source: str, entries: List[FieldDictionaryEntry]) -> None:
        self._ensure_dir(source)
        path = self._field_observations_path(source)
        with open(path, "a", encoding="utf-8") as fh:
            for e in entries:
                fh.write(e.model_dump_json() + "\n")

    def load_run_manifest(self, source: str) -> Optional[RunManifest]:
        path = self._run_manifest_path(source)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return RunManifest.model_validate_json(fh.read())

    def catalog_exists(self, source: str) -> bool:
        return self._catalog_exists(source)

    # ------------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------------

    def family_counts(self, source: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.load(source):
            counts[e.page_family] = counts.get(e.page_family, 0) + 1
        return counts

    def export_markdown_summary(self, source: str) -> str:
        counts = self.family_counts(source)
        manifest = self.load_run_manifest(source)
        lines = [f"# Catalog Summary — {source}", ""]
        if manifest:
            lines += [
                f"Run ID: `{manifest.run_id}`",
                f"Mode: {manifest.mode}",
                f"Seeds: {manifest.seed_count}",
                f"Fetched: {manifest.pages_fetched}",
                f"Network requests: {manifest.network_requests}",
                f"Stop reason: {manifest.stop_reason or 'completed normally'}",
                "",
            ]
        lines += ["| Family | Count |", "|--------|-------|"]
        for family, count in sorted(counts.items()):
            lines.append(f"| {family} | {count} |")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _known_parser_families(source: str) -> frozenset[str]:
    """Families that have at least a partial parser implementation."""
    if source == "soccerstats":
        return frozenset({"matches", "match_preview"})
    if source == "forebet":
        return frozenset({"daily_predictions"})
    return frozenset()


def _complete_parser_families(source: str) -> frozenset[str]:
    """Families whose parser is considered complete per current codebase."""
    # Deliberately conservative — none are fully validated against live data yet.
    return frozenset()


def _guess_playwright(entry: CatalogEntry) -> str:
    """Heuristically guess whether Playwright may be required."""
    if entry.scripts_found > 5:
        return "suspected"
    if entry.tables_found == 0 and entry.links_found < 5:
        return "suspected"
    return "no"


def content_hash(data: bytes) -> str:
    """Return hex SHA-256 of *data*."""
    return sha256(data).hexdigest()

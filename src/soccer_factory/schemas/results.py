"""Lossless and semantic extraction of public SoccerStats result-detail pages."""
from __future__ import annotations

import re
from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from bs4 import BeautifulSoup


def _text(node: Any) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


class Grading(BaseModel):
    model_config = ConfigDict(strict=True)
    prediction_id: str
    match_id: str
    correct: Optional[bool] = None
    actual_outcome: Optional[str] = None
    final_score: Optional[str] = None
    total_goals: Optional[int] = None
    btts_result: Optional[bool] = None
    graded_at: datetime
    grading_source: str
    unresolved_status: Optional[str] = None


class Result(BaseModel):
    model_config = ConfigDict(strict=True)
    match_id: str
    status: str = "unknown"
    home_score: Optional[int] = Field(default=None, ge=0)
    away_score: Optional[int] = Field(default=None, ge=0)
    match_outcome: Optional[str] = Field(default=None)
    total_goals: Optional[int] = Field(default=None, ge=0)
    btts_result: Optional[bool] = Field(default=None)
    over_25_result: Optional[bool] = Field(default=None)


def extract_result_detail(content: bytes) -> dict[str, Any]:
    """Return every non-empty public HTML table as structured rows."""
    soup = BeautifulSoup(content, "lxml")
    title = _text(soup.title) if soup.title else ""
    tables = []
    for index, table in enumerate(soup.find_all("table"), start=1):
        rows = []
        for tr in table.find_all("tr", recursive=False):
            cells = [_text(cell) for cell in tr.find_all(["td", "th"], recursive=False)]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append({"table_index": index, "rows": rows})
    headings = []
    for heading in soup.find_all(["h1", "h2", "h3"]):
        value = _text(heading)
        if value and value not in headings:
            headings.append(value)
    return {"page_title": title, "headings": headings, "tables": tables}


def summarize_result_detail(content: bytes, home_team: str, away_team: str) -> dict[str, Any]:
    """Extract only explicit match-level facts; retain the lossless archive too."""
    text = _text(BeautifulSoup(content, "lxml"))

    def pair(pattern: str) -> dict[str, int] | None:
        found = re.search(pattern, text, re.I)
        if not found:
            return None
        return {"home": int(found.group(1)), "away": int(found.group(2))}

    final_score = pair(
        re.escape(home_team) + r"\s+(\d+)\s*(?::|\s)\s*(\d+)\s+" + re.escape(away_team)
    )
    half_time = pair(r"Half-time score:\s*\(\s*(\d+)\s*[-:]\s*(\d+)\s*\)")

    match_stats: dict[str, Any] = {}
    for name, pattern in {
        "ball_possession": r"Ball possession\s+(\d+)%\s+(\d+)%",
        "corners": r"Corners\s+(\d+)\s+(\d+)",
        "time_leading": r"% of time leading\s+(\d+)%\s+(\d+)%",
        "domination_index": r"Domination Index\s+(\d+)%\s+(\d+)%",
    }.items():
        found = pair(pattern)
        if found is not None:
            match_stats[name] = found
    surprise = re.search(r"(?:Outcome )?Surprise-Level:\s*(\d+(?:\.\d+)?)%", text, re.I)
    if surprise:
        match_stats["outcome_surprise_level"] = float(surprise.group(1))

    return {
        "final_score": final_score,
        "half_time_score": half_time,
        "total_goals": (final_score["home"] + final_score["away"]) if final_score else None,
        "btts": bool(final_score and final_score["home"] > 0 and final_score["away"] > 0),
        "match_stats": match_stats,
    }

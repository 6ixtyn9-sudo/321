"""Lossless structured extraction of public SoccerStats result-detail pages."""
from __future__ import annotations

from bs4 import BeautifulSoup
from typing import Any


def _text(node: Any) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def extract_result_detail(content: bytes) -> dict[str, Any]:
    """Return every non-empty HTML table as labelled rows without interpretation.

    This is deliberately broad: it preserves all public statistical material for
    later semantic parsers, rather than discarding sections we do not yet model.
    """
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

"""Lossless structured extraction of public SoccerStats result-detail pages."""
from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup


def _text(node: Any) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def extract_result_detail(content: bytes) -> dict[str, Any]:
    """Preserve every non-empty public HTML table as structured rows."""
    soup = BeautifulSoup(content, "lxml")

    title = _text(soup.title) if soup.title else ""
    headings: list[str] = []

    for heading in soup.find_all(["h1", "h2", "h3"]):
        value = _text(heading)
        if value and value not in headings:
            headings.append(value)

    tables: list[dict[str, Any]] = []

    for index, table in enumerate(soup.find_all("table"), start=1):
        rows: list[list[str]] = []

        for tr in table.find_all("tr", recursive=False):
            cells = [
                _text(cell)
                for cell in tr.find_all(["td", "th"], recursive=False)
            ]

            if any(cells):
                rows.append(cells)

        if rows:
            tables.append(
                {
                    "table_index": index,
                    "rows": rows,
                }
            )

    return {
        "page_title": title,
        "headings": headings,
        "tables": tables,
    }

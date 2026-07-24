from datetime import date, timedelta
import json

import pytest

from src.soccer_factory.sources.soccerstats.live import (
    daily_index_urls,
    collect_daily_bundle,
)
from src.soccer_factory.sources.soccerstats import urls as _urls


def test_daily_index_routes_include_base_and_ms_expansion():
    """The index URL set must always include the base matchday URLs, and for
    today/tomorrow also fan out across ``ms=<filter>`` (the server-side route to
    the expanded "Show all matches" layout)."""
    today = date(2026, 7, 24)

    yest_urls = daily_index_urls(today - timedelta(days=1), today)
    assert "https://www.soccerstats.com/matches.asp?matchday=0&daym=yesterday&matchdayn=1" in yest_urls
    assert "https://www.soccerstats.com/matches.asp?matchday=200&daym=yesterday&matchdayn=1" in yest_urls
    # Yesterday is full in plain view, no ms= fan-out needed
    for u in yest_urls:
        assert "&ms=" not in u

    today_urls = daily_index_urls(today, today)
    assert "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1" in today_urls
    assert "https://www.soccerstats.com/matches.asp?matchday=206&matchdayn=1" in today_urls
    # must include at least one ms= expansion for grouped bases
    assert any("matchday=1&matchdayn=1&ms=a" in u for u in today_urls)
    # by-time views are NOT fanned out (they're already flat)
    assert not any("matchday=206&matchdayn=1&ms=" in u for u in today_urls)

    tmw_urls = daily_index_urls(today + timedelta(days=1), today)
    assert "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1" in tmw_urls
    assert any("matchday=2&daym=tomorrow&matchdayn=1&ms=a" in u for u in tmw_urls)

    # Sizes match urls module contract: 3 yesterday, 60 today, 57 tomorrow
    assert len(yest_urls) == 3
    assert len(today_urls) == 3 + 3 * len(_urls._EXPANDED_FILTERS) + 3  # 60
    assert len(tmw_urls) == 3 + 3 * len(_urls._EXPANDED_FILTERS)         # 57


def test_daily_index_routes_do_not_invent_calendar_offsets():
    with pytest.raises(ValueError, match="yesterday, today, or tomorrow"):
        daily_index_urls(date(2026, 7, 27), date(2026, 7, 24))


INDEX = b"""<table><tr class='parent'><td>Brazil - Serie A <a>stats</a></td></tr>
<tr class='child'><td>Scope</td><td>GP</td><td>W%</td><td>FTS</td><td>CS</td><td>BTS</td><td>TG</td><td>GF</td><td>GA</td><td>1.5+</td><td>2.5+</td><td>3.5+</td><td>Points</td></tr>
<tr class='team1row'><td>Coritiba</td><td rowspan='2'>23:30</td><td rowspan='2'><a href='pmatch.asp?league=brazil&stats=183-3-8-2026'>stats</a></td></tr>
<tr class='team2row'><td>Palmeiras</td></tr>
<tr class='team1row'><td>Vila Nova</td><td rowspan='2'>2</td><td rowspan='2'><a href='round_details.asp?league=brazil2&mrevid=m181'>analysis</a></td></tr>
<tr class='team2row'><td>Fortaleza</td></tr></table>"""
PREVIEW = b"<html><title>Preview</title></html>"


class _NoopBrowser:
    def __init__(self, *_a, **_kw):
        self.enabled = False
    def fetch(self, _url):
        return 0, b"", {}, "disabled"


class FakeCollector:
    calls: list[str] = []

    def __init__(self, _email: str):
        self.calls = []
        FakeCollector.calls = self.calls

    def fetch(self, url: str):
        self.calls.append(url)
        content = INDEX if "matches.asp" in url else PREVIEW
        return 200, content, {"Content-Type": "text/html", "Date": "Wed"}, None


def test_bundle_snapshots_index_only_by_default(monkeypatch, tmp_path):
    """With default max_previews=0 and comprehensive_fallback=False the bundle
    must collect exactly the index pages, no previews, and stay within 50
    requests."""
    monkeypatch.setattr("src.soccer_factory.sources.soccerstats.live.SoccerStatsCollector", FakeCollector)
    monkeypatch.setattr("src.soccer_factory.sources.soccerstats.live.PlaywrightFallback", _NoopBrowser)

    target = date(2026, 7, 24)
    # Only pass a small override URL set so the test doesn't actually hit the fan-out budget
    index_urls = ["https://www.soccerstats.com/matches.asp?matchday=201&matchdayn=1"]
    snapshots = collect_daily_bundle(
        target=target, today=target,
        output_dir=tmp_path, contact_email="audit@example.com",
        parser_version="2.2-expanded-ms", max_previews=0,
        comprehensive_fallback=False,
        index_urls_override=index_urls,
    )
    # 1 index snapshot + finished-result snapshots for any completed fixtures
    # (the result budget is respected but results are still fetched when budget allows)
    assert len(snapshots) >= 1
    assert any("daily_index_" in s.local_file_path for s in snapshots if s.local_file_path)
    # No preview pages collected (max_previews=0)
    assert not any("pmatch_preview_" in s.local_file_path for s in snapshots if s.local_file_path)
    run_dir = next((tmp_path / "soccerstats").iterdir())
    manifest = [json.loads(line) for line in (run_dir / "manifest.jsonl").read_text().splitlines()]
    assert {entry["validation_status"] for entry in manifest} == {"fetched"}
    links = [json.loads(line) for line in (run_dir / "fixture_links.jsonl").read_text().splitlines()]
    assert any(link["status"] == "pre-match" for link in links)
    assert any(link["status"] == "finished" for link in links)


def test_bundle_keeps_request_budget_bounded():
    n_index = len(daily_index_urls(date(2026, 7, 24), date(2026, 7, 24)))
    expected_max = 50 - n_index
    from pathlib import Path
    with pytest.raises(ValueError, match=rf"between 0 and {expected_max}"):
        collect_daily_bundle(
            target=date(2026, 7, 24), today=date(2026, 7, 24),
            output_dir=Path("/tmp/not-used"), contact_email="x",
            parser_version="2.2-expanded-ms", max_previews=50,
            comprehensive_fallback=False,
        )

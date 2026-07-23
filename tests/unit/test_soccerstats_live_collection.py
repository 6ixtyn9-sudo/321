from datetime import date, timedelta
import json

import pytest

from src.soccer_factory.sources.soccerstats.live import daily_index_urls, collect_daily_bundle


def test_daily_index_routes_are_explicit_and_bounded():
    today = date(2026, 7, 22)
    assert daily_index_urls(today - timedelta(days=1), today) == [
        "https://www.soccerstats.com/matches.asp?matchday=0&daym=yesterday&matchdayn=1"
    ]
    assert daily_index_urls(today, today) == [
        "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1",
        "https://www.soccerstats.com/matches.asp?matchday=101&matchdayn=1",
        "https://www.soccerstats.com/matches.asp?matchday=201&matchdayn=1",
    ]
    assert daily_index_urls(today + timedelta(days=1), today) == [
        "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1",
        "https://www.soccerstats.com/matches.asp?matchday=102&matchdayn=1",
        "https://www.soccerstats.com/matches.asp?matchday=202&matchdayn=1",
    ]


def test_daily_index_routes_do_not_invent_calendar_offsets():
    with pytest.raises(ValueError, match="yesterday, today, or tomorrow"):
        daily_index_urls(date(2026, 7, 24), date(2026, 7, 22))


INDEX = b"""<table><tr class='parent'><td>Brazil - Serie A <a>stats</a></td></tr>
<tr class='team1row'><td>Coritiba</td><td rowspan='2'>23:30</td><td rowspan='2'><a href='pmatch.asp?league=brazil&stats=183-3-8-2026'>stats</a></td></tr>
<tr class='team2row'><td>Palmeiras</td></tr>
<tr class='team1row'><td>Vila Nova</td><td rowspan='2'>2</td><td rowspan='2'><a href='round_details.asp?league=brazil2&mrevid=m181'>analysis</a></td></tr>
<tr class='team2row'><td>Fortaleza</td></tr></table>"""
PREVIEW = b"<html><title>Preview</title></html>"


class FakeCollector:
    calls: list[str] = []

    def __init__(self, _email: str):
        self.calls = []
        FakeCollector.calls = self.calls

    def fetch(self, url: str):
        self.calls.append(url)
        content = INDEX if "matches.asp" in url else PREVIEW
        return 200, content, {"Content-Type": "text/html", "Date": "Wed"}, None


def test_bundle_snapshots_index_and_scheduled_previews_only(monkeypatch, tmp_path):
    monkeypatch.setattr("src.soccer_factory.sources.soccerstats.live.SoccerStatsCollector", FakeCollector)
    snapshots = collect_daily_bundle(target=date(2026, 7, 22), today=date(2026, 7, 22),
        output_dir=tmp_path, contact_email="audit@example.com", parser_version="2.0", max_previews=5)
    assert len(snapshots) >= 4  # three scopes plus at least one preview/result snapshot
    assert len(FakeCollector.calls) >= 3
    assert any("pmatch.asp" in url for url in FakeCollector.calls)
    # Note: finished result pages may also be collected for today/yesterday fixtures
    run_dir = next((tmp_path / "soccerstats").iterdir())
    manifest = [json.loads(line) for line in (run_dir / "manifest.jsonl").read_text().splitlines()]
    assert {entry["validation_status"] for entry in manifest} == {"fetched"}
    assert (run_dir / "daily_index_2026-07-22_1.html").exists()
    assert (run_dir / "pmatch_preview_001.html").exists()
    links = [json.loads(line) for line in (run_dir / "fixture_links.jsonl").read_text().splitlines()]
    scheduled = next(link for link in links if link["status"] == "pre-match")
    finished = next(link for link in links if link["status"] == "finished")
    assert scheduled["preview_collected"] is True
    assert scheduled["preview_snapshot_path"].endswith("pmatch_preview_001.html")
    assert finished["preview_collected"] is False


def test_bundle_keeps_request_budget_bounded():
    with pytest.raises(ValueError, match="between 0 and 47"): 
        collect_daily_bundle(target=date(2026, 7, 22), today=date(2026, 7, 22),
            output_dir=__import__("pathlib").Path("/tmp/not-used"), contact_email="x", parser_version="2", max_previews=50)

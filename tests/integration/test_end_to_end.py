import pytest
import os
import json
import shutil

from src.soccer_factory.cli import main

def test_end_to_end_fixture_mode(monkeypatch, tmp_path):
    # Setup args
    test_args = ["cli", "run-daily", "--date", "2026-07-21", "--mode", "fixture"]
    monkeypatch.setattr("sys.argv", test_args)

    # Clean dirs
    for d in ["data/raw", "data/interim", "data/processed", "data/reports"]:
        if os.path.exists(d):
            shutil.rmtree(d)

    main()

    # Assertions
    assert os.path.exists("data/raw/manifest.json")
    with open("data/raw/manifest.json") as f:
        raw_manifest = json.load(f)
        assert raw_manifest["mode"] == "fixture"

    assert os.path.exists("data/interim/matches.json")
    assert os.path.exists("data/interim/observations.json")
    assert os.path.exists("data/interim/features.json")

    assert os.path.exists("data/processed/joined.json")
    with open("data/processed/joined.json") as f:
        joined = json.load(f)
        # We expect at least one cross-source match (e.g. Manchester Utd vs Arsenal)
        assert len(joined) > 0
        
    with open("data/processed/manifest.json") as f:
        proc_manifest = json.load(f)
        assert proc_manifest["quarantined"] > 0
        assert proc_manifest["joined"] > 0

    assert os.path.exists("data/processed/predictions.json")
    with open("data/processed/predictions.json") as f:
        preds = json.load(f)
        assert len(preds) > 0
        assert all(p["probability"] >= 0.0 and p["probability"] <= 1.0 for p in preds)
        markets = set(p["market"] for p in preds)
        assert "1X2" in markets or "Double chance" in markets or "Over/Under 2.5" in markets or "BTTS" in markets

    assert os.path.exists("data/reports/report_2026-07-21.json")
    with open("data/reports/report_2026-07-21.json") as f:
        frozen_preds = json.load(f)
        assert len(frozen_preds) == len(preds)
        assert all(p["frozen_at"] is not None for p in frozen_preds)

def test_live_mode_refusal(monkeypatch, capsys):
    test_args = ["cli", "collect", "--date", "2026-07-21", "--mode", "live"]
    monkeypatch.setattr("sys.argv", test_args)

    with pytest.raises(SystemExit) as e:
        main()
    
    assert e.value.code == 1
    captured = capsys.readouterr()
    assert "--confirm-live flag" in captured.err

def test_health_check(monkeypatch, capsys):
    test_args = ["cli", "health-check"]
    monkeypatch.setattr("sys.argv", test_args)

    main()
    captured = capsys.readouterr()
    assert "parser status: OK" in captured.out

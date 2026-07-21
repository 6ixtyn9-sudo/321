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
        assert len(joined) > 0
        
    with open("data/processed/manifest.json") as f:
        proc_manifest = json.load(f)
        assert proc_manifest["quarantined"] > 0
        assert proc_manifest["joined"] > 0

    assert os.path.exists("data/processed/predictions.json")
    with open("data/processed/predictions.json") as f:
        preds = json.load(f)
        assert len(preds) == 4  # 1 match with features x 4 canonical markets
        assert all(p["probability"] >= 0.0 and p["probability"] <= 1.0 for p in preds)
        markets = set(p["market"] for p in preds)
        assert markets == {"1x2", "double_chance", "over25", "btts"}

    assert os.path.exists("data/processed/no_predictions.json")
    with open("data/processed/no_predictions.json") as f:
        no_preds = json.load(f)
        # Each unmatched / no-feature match receives 4 canonical market no-predictions.
        # Exact count depends on fixture data; verify structure instead of hardcoding.
        assert len(no_preds) > 0
        assert len(no_preds) % 4 == 0, "no-predictions must be a multiple of 4 (one per market)"
        assert all(p["status"] == "no_prediction" for p in no_preds)
        assert all(p["market"] in {"1x2", "double_chance", "over25", "btts"} for p in no_preds)

    assert os.path.exists("data/reports/report_2026-07-21.json")
    with open("data/reports/report_2026-07-21.json") as f:
        report_data = json.load(f)
        assert len(report_data["predictions"]) == 4
        assert len(report_data["no_predictions"]) > 0
        total_pairs = report_data["summary"]["total_match_market_pairs"]
        # total = predictions + no_predictions, all multiples of 4
        assert total_pairs == len(report_data["predictions"]) + len(report_data["no_predictions"])
        assert total_pairs % 4 == 0

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

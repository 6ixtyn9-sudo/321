import pytest
import os
import argparse
from unittest.mock import patch, MagicMock
from src.soccer_factory.cli import check_mode, do_discover, parse_args
from src.soccer_factory.discovery.models import RunManifest

def test_live_mode_refusal(capsys):
    with patch("sys.argv", ["cli.py", "discover", "--source", "soccerstats", "--mode", "live"]):
        args = parse_args()
        with pytest.raises(SystemExit) as exc:
            check_mode(args)
        assert exc.value.code == 1
        out, err = capsys.readouterr()
        assert "Error: --mode live requires --confirm-live flag" in err

def test_fixture_mode_zero_network(tmp_path):
    with patch("sys.argv", ["cli.py", "discover", "--source", "soccerstats", "--mode", "fixture"]):
        args = parse_args()
        dummy_manifest = RunManifest(run_id="test", git_commit="", source="soccerstats", mode="fixture")
        with patch("src.soccer_factory.discovery.crawler.BoundedCrawler.crawl", return_value=([], dummy_manifest)) as mock_crawl:
            with patch("src.soccer_factory.discovery.catalog.CatalogStore"):
                do_discover(args)
                mock_crawl.assert_called()

def test_live_mode_separation(tmp_path):
    with patch("sys.argv", ["cli.py", "discover", "--source", "soccerstats", "--mode", "live", "--confirm-live"]):
        args = parse_args()
        dummy_manifest = RunManifest(run_id="test", git_commit="", source="soccerstats", mode="live")
        with patch("src.soccer_factory.discovery.catalog.CatalogStore") as mock_store_class:
            with patch("src.soccer_factory.discovery.crawler.BoundedCrawler.crawl", return_value=([], dummy_manifest)):
                do_discover(args)
                mock_store_class.assert_called_with(catalog_dir='data/catalog_live_audit')

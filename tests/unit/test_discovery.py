import pytest
from datetime import datetime, timezone
from src.soccer_factory.discovery.policy import is_allowed, is_restricted, is_same_domain, is_valid_scheme
from src.soccer_factory.discovery.classifier import classify, classify_outcome, all_families
from src.soccer_factory.discovery.crawler import BoundedCrawler, normalize_url, CircuitBreaker, RateLimiter, CircuitOpenError
from src.soccer_factory.discovery.models import DiscoveryConfig, CatalogEntry, RunManifest
from src.soccer_factory.discovery.catalog import CatalogStore

class TestURLHandling:
    def test_fragment_stripping(self):
        assert normalize_url("https://soccerstats.com/foo#bar") == "https://soccerstats.com/foo"
        assert normalize_url("https://soccerstats.com/#top") == "https://soccerstats.com/"
        
    def test_lowercase_scheme_and_hostname(self):
        assert normalize_url("HTTPS://SoccerStats.com/Foo") == "https://soccerstats.com/Foo"
        
    def test_query_parameter_sorting(self):
        assert normalize_url("https://soccerstats.com/x?b=2&a=1") == "https://soccerstats.com/x?a=1&b=2"
        
    def test_semantically_distinct_query_parameters_remain_distinct(self):
        assert normalize_url("https://soccerstats.com/x?a=1") != normalize_url("https://soccerstats.com/x?a=2")
        
    def test_default_port_normalization(self):
        assert normalize_url("https://soccerstats.com:443/foo") == "https://soccerstats.com/foo"
        assert normalize_url("http://soccerstats.com:80/foo") == "http://soccerstats.com/foo"
        assert normalize_url("http://soccerstats.com:8080/foo") == "http://soccerstats.com:8080/foo"

class TestPolicy:
    def test_same_domain_allowlist(self):
        assert is_same_domain("https://soccerstats.com/matches", "soccerstats")
        assert is_same_domain("https://www.soccerstats.com/matches", "soccerstats")
        assert is_same_domain("https://www.forebet.com/tips", "forebet")
        
    def test_external_domain_rejection(self):
        assert not is_same_domain("https://data.soccerstats.com/foo", "soccerstats")
        assert not is_same_domain("https://google.com/", "soccerstats")
        
    def test_invalid_scheme_rejection(self):
        assert not is_valid_scheme("mailto:admin@soccerstats.com")
        assert not is_valid_scheme("javascript:void(0)")
        assert not is_valid_scheme("tel:12345")
        assert not is_valid_scheme("data:text/html,<html>")
        assert not is_valid_scheme("//cdn.soccerstats.com/js")
        
    def test_restricted_paths(self):
        assert is_restricted("https://soccerstats.com/members.asp")
        assert is_restricted("https://soccerstats.com/register.asp")
        assert is_restricted("https://soccerstats.com/cdn-cgi/login")
        assert is_restricted("https://soccerstats.com/js/app.js")
        assert is_restricted("https://soccerstats.com/logo.png")
        assert not is_restricted("https://soccerstats.com/matches.asp")

class TestClassification:
    def test_soccerstats_families(self):
        assert classify("https://soccerstats.com/matches.asp", "soccerstats") == "matches"
        assert classify("https://soccerstats.com/pmatch.asp?league=england", "soccerstats") == "match_preview"
        assert classify("https://soccerstats.com/latest.asp", "soccerstats") == "league_latest"
        assert classify("https://soccerstats.com/leagueview.asp", "soccerstats") == "league_view"
        assert classify("https://soccerstats.com/round_details.asp?league=ecuador&mrevid=m160&st1=13&st2=16", "soccerstats") == "round_details"
        assert classify("https://soccerstats.com/results.asp", "soccerstats") == "results"
        assert classify("https://soccerstats.com/stats.asp", "soccerstats") == "statistical_overview"
        assert classify("https://soccerstats.com/faq.asp", "soccerstats") == "faq"
        assert classify("https://soccerstats.com/stats.asp?type=over_under", "soccerstats") == "over_under"
        assert classify("https://soccerstats.com/stats.asp?type=home_advantage", "soccerstats") == "home_advantage"

    def test_forebet_families(self):
        assert classify("https://forebet.com/en/football-tips-and-predictions-for-today", "forebet") == "daily_predictions"
        assert classify("https://forebet.com/en/football-tips-and-predictions-for-tomorrow", "forebet") == "tomorrow_predictions"
        assert classify("https://forebet.com/en/football-tips-and-predictions-for-the-weekend", "forebet") == "weekend_predictions"
        assert classify("https://forebet.com/en/football-predictions-from-yesterday", "forebet") == "finished_predictions"
        assert classify("https://forebet.com/en/live-football-tips", "forebet") == "live_predictions"
        assert classify("https://forebet.com/en/football/matches/atletico-mineiro-bahia-2418076", "forebet") == "football_match"
        assert classify("https://forebet.com/en/football-match-previews/28554-atletico-mineiro-seek-home-edge-against-bahia-in-tricky-brasileiro-serie-a-clash", "forebet") == "match_preview_article"
        assert classify("https://forebet.com/en/football-match-previews", "forebet") == "match_preview_index"
        assert classify("https://forebet.com/en/livescore", "forebet") == "livescore"
        assert classify("https://forebet.com/en/injured-players", "forebet") == "injured_players"
        assert classify("https://forebet.com/en/team-comparison", "forebet") == "team_comparison"
        
    def test_values_and_non_soccer(self):
        assert classify_outcome("https://forebet.com/en/value-bets", "forebet") == ("values_or_odds", "values_or_odds")
        assert classify_outcome("https://forebet.com/en/basketball", "forebet") == ("non_soccer", "non_soccer")
        assert classify_outcome("https://forebet.com/en/tennis", "forebet") == ("non_soccer", "non_soccer")
        
    def test_unknown_family(self):
        assert classify("https://soccerstats.com/some-unknown-path.asp", "soccerstats") == "unknown"
        
    def test_classify_outcome(self):
        cat, fam = classify_outcome("https://soccerstats.com/matches.asp", "soccerstats")
        assert cat == "known"
        assert fam == "matches"
        
        cat, fam = classify_outcome("https://soccerstats.com/some-unknown-path.asp", "soccerstats")
        assert cat == "unknown"
        assert fam == "unknown"
        
        cat, fam = classify_outcome("javascript:void(0)", "soccerstats")
        assert cat == "restricted"
        assert fam == "restricted"
        
        cat, fam = classify_outcome("https://google.com/", "soccerstats")
        assert cat == "external"
        assert fam == "external"

class TestCrawlerLimits:
    def test_circuit_breaker(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure(404)
        assert not cb.is_open
        
        cb.record_failure(403)
        cb.record_failure(429)
        assert not cb.is_open
        
        cb.record_failure(429)
        assert cb.is_open
        
        with pytest.raises(CircuitOpenError):
            cb.check()
            
    def test_circuit_breaker_reset(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure(403)
        cb.record_failure(403)
        cb.record_success() # Reset
        cb.record_failure(403)
        assert not cb.is_open

class TestCatalog:
    def test_append_only_behavior(self, tmp_path):
        store = CatalogStore(catalog_dir=str(tmp_path))
        entry1 = CatalogEntry(source="soccerstats", url="http://x.com", canonical_url="http://x.com", content_hash="hash1")
        store.append(entry1)
        
        entry2 = CatalogEntry(source="soccerstats", url="http://x.com", canonical_url="http://x.com", content_hash="hash2")
        store.append(entry2)
        
        loaded = store.load("soccerstats")
        assert len(loaded) == 2
        assert loaded[0].content_hash == "hash1"
        assert loaded[1].content_hash == "hash2"

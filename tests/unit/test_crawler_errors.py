import pytest
import urllib.robotparser
from src.soccer_factory.discovery.policy import is_allowed, is_valid_scheme, is_same_domain, is_restricted
from src.soccer_factory.discovery.crawler import BoundedCrawler, CircuitBreaker, CircuitOpenError, RateLimiter
from src.soccer_factory.discovery.catalog import CatalogStore
from src.soccer_factory.discovery.models import DiscoveryConfig, CatalogEntry
from src.soccer_factory.sources.http_collector import RateLimitError

def test_circuit_breaker():
    cb = CircuitBreaker(threshold=3)
    cb.record_success()
    cb.check()
    cb.record_failure(403)
    cb.record_failure(429)
    cb.record_failure(403)
    with pytest.raises(CircuitOpenError):
        cb.check()

def test_rate_limiter():
    limiter = RateLimiter(max_rpm=60000, delay_seconds=0.001)
    limiter.throttle() # Should not raise
    
def test_policy_is_valid_scheme():
    assert is_valid_scheme("http://example.com") is True
    assert is_valid_scheme("https://example.com") is True
    assert is_valid_scheme("ftp://example.com") is False
    assert is_valid_scheme("mailto:test@example.com") is False

def test_policy_is_restricted():
    assert is_restricted("https://example.com/assets/img.png") is True
    assert is_restricted("https://example.com/css/style.css") is True
    assert is_restricted("https://example.com/js/app.js") is True
    assert is_restricted("https://example.com/cdn-cgi/trace") is True
    assert is_restricted("https://example.com/matches.asp") is False

def test_catalog_append_only(tmp_path):
    store = CatalogStore(catalog_dir=str(tmp_path))
    entry1 = CatalogEntry(source="test", url="http://example.com", canonical_url="http://example.com", page_family="unknown", discovery_status="discovered")
    store.append(entry1)
    assert len(store.load("test")) == 1
    
    # Missing catalog loads empty
    assert len(store.load("missing")) == 0

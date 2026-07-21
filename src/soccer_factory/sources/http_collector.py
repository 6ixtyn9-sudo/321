import requests
import time
from typing import Tuple, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .base import BaseCollector

class CircuitBreakerError(Exception):
    pass

class RateLimitError(Exception):
    pass

class HttpCollector(BaseCollector):
    def __init__(self, user_agent: str, delay: float = 2.0, max_requests: int = 100):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.delay = delay
        self.max_requests = max_requests
        self.request_count = 0
        self.consecutive_errors = 0
        self.circuit_open = False
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, RateLimitError))
    )
    def _do_fetch(self, url: str) -> requests.Response:
        if self.circuit_open:
            raise CircuitBreakerError("Circuit breaker is open due to repeated failures.")
            
        if self.request_count >= self.max_requests:
            raise RateLimitError(f"Max requests ({self.max_requests}) reached for this run.")
            
        time.sleep(self.delay)
        self.request_count += 1
        
        try:
            resp = self.session.get(url, timeout=15)
            
            if resp.status_code in (403, 429):
                self.consecutive_errors += 1
                if self.consecutive_errors >= 3:
                    self.circuit_open = True
                
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(int(retry_after))
                    
                raise RateLimitError(f"Rate limited or forbidden: {resp.status_code}")
                
            resp.raise_for_status()
            self.consecutive_errors = 0
            return resp
            
        except requests.exceptions.RequestException as e:
            self.consecutive_errors += 1
            if self.consecutive_errors >= 5:
                self.circuit_open = True
            raise e

    def fetch(self, url: str) -> Tuple[int, bytes, Dict[str, str], Optional[str]]:
        try:
            resp = self._do_fetch(url)
            return resp.status_code, resp.content, dict(resp.headers), None
        except Exception as e:
            # If it fails completely after retries
            return 0, b"", {}, str(e)

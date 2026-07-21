from playwright.sync_api import sync_playwright
from typing import Tuple, Dict, Optional

class PlaywrightFallback:
    def __init__(self, user_agent: str, enabled: bool = False):
        self.user_agent = user_agent
        self.enabled = enabled

    def fetch(self, url: str) -> Tuple[int, bytes, Dict[str, str], Optional[str]]:
        if not self.enabled:
            return 0, b"", {}, "Playwright is disabled."
            
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.user_agent)
                page = context.new_page()
                
                # Navigate and wait for network idle to ensure dynamic content loads
                response = page.goto(url, wait_until="networkidle", timeout=30000)
                
                if not response:
                    return 0, b"", {}, "No response from Playwright"
                    
                status_code = response.status
                headers = response.headers
                content = page.content().encode('utf-8')
                
                browser.close()
                return status_code, content, headers, None
                
        except Exception as e:
            return 0, b"", {}, str(e)

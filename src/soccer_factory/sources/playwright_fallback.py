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

                # Try to safely expand public visible controls like "Show all matches"
                expanded_content = page.content().encode('utf-8')
                try:
                    # Look for common expanded control patterns
                    selectors = [
                        'a[href*="matchday=0"]',
                        'a[href*="matchday=1"]',
                        'a[href*="show_all"]',
                        'a:has-text("Show all matches")',
                        'a:has-text("Show all")',
                        'button:has-text("Show all")',
                    ]
                    for selector in selectors:
                        elements = page.query_selector_all(selector)
                        for el in elements:
                            try:
                                el.click(timeout=5000)
                                page.wait_for_timeout(500)
                                expanded_content = page.content().encode('utf-8')
                            except Exception:
                                pass
                except Exception:
                    pass
                    
                status_code = response.status
                headers = response.headers
                content = expanded_content if expanded_content else page.content().encode('utf-8')
                
                browser.close()
                return status_code, content, headers, None
                
        except Exception as e:
            return 0, b"", {}, str(e)

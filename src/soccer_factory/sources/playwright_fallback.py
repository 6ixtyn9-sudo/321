"""Playwright-powered browser fallback for SoccerStats (and similar) pages.

When the server returns the featured-only HTML, a real browser can execute the
page's jQuery to reveal child rows.  SoccerStats also gates full league listings
behind a SELECTION > "All matches" toggle; the fallback here:

  1. Dismisses any cookie/consent overlay.
  2. Forces every ``table.detail tr`` visible via injected JS (undoes the
     ``$childRows.hide()`` the page does on load).
  3. Clicks the "All matches" / "Show all matches" control via JS in case it's
     available.
  4. Re-applies the visibility force after clicks.

The URL fan-out across ``ms=<filter>`` parameters already returns the expanded
layout server-side in pure HTTP requests (no browser needed); the Playwright
fallback is reserved for when a user explicitly opts in and provides
``browser_fallback=True``.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from playwright.sync_api import sync_playwright


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

                response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if not response:
                    browser.close()
                    return 0, b"", {}, "No response from Playwright"

                # Dismiss common cookie overlays
                for sel in (
                    'button:has-text("Accept")',
                    'button:has-text("I agree")',
                    'button:has-text("AGREE")',
                    'a:has-text("Accept")',
                    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                    '.fc-button-label',
                ):
                    try:
                        el = page.query_selector(sel)
                        if el:
                            el.click(timeout=1500)
                            page.wait_for_timeout(300)
                    except Exception:
                        pass

                # Force-show every table row (undoes $childRows.hide())
                def _force_show() -> None:
                    try:
                        page.evaluate(
                            """
                            () => {
                                document.querySelectorAll('table tr').forEach(tr => {
                                    tr.style.display = '';
                                    tr.removeAttribute('hidden');
                                    tr.classList.remove('hidden');
                                });
                                // Some builds toggle a .child class visibility too
                                document.querySelectorAll('tr.child').forEach(tr => {
                                    tr.style.display = '';
                                });
                            }
                            """
                        )
                    except Exception:
                        pass

                _force_show()

                # Try clicking the "All matches" / "Show all matches" controls
                for sel in (
                    'a:has-text("All matches")',
                    'a:has-text("Show all matches")',
                    'a:has-text("Show all")',
                    'button:has-text("Show all")',
                    'a:has-text("All")',
                ):
                    try:
                        for el in page.query_selector_all(sel):
                            try:
                                el.scroll_into_view_if_needed(timeout=1000)
                                page.evaluate("(e) => e.click()", el)
                                page.wait_for_timeout(400)
                            except Exception:
                                pass
                    except Exception:
                        pass

                _force_show()
                page.wait_for_timeout(500)

                status_code = response.status
                headers = response.headers
                content = page.content().encode("utf-8")

                browser.close()
                return status_code, content, headers, None

        except Exception as e:
            return 0, b"", {}, str(e)

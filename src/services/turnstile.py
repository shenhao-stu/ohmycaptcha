"""Cloudflare Turnstile solver using Playwright browser automation.

Supports TurnstileTaskProxyless and TurnstileTaskProxylessM1 task types.
Visits the target page, interacts with the Turnstile widget, and extracts the token.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import Browser, Playwright, async_playwright

from ..core.config import Config

log = logging.getLogger(__name__)

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
"""

_EXTRACT_TURNSTILE_TOKEN_JS = """
() => {
    // Check for Turnstile response input
    const input = document.querySelector('[name="cf-turnstile-response"]')
        || document.querySelector('input[name*="turnstile"]');
    if (input && input.value && input.value.length > 20) {
        return input.value;
    }
    // Try the turnstile API
    if (window.turnstile && typeof window.turnstile.getResponse === 'function') {
        const resp = window.turnstile.getResponse();
        if (resp && resp.length > 20) return resp;
    }
    return null;
}
"""


class TurnstileSolver:
    """Solves Cloudflare Turnstile tasks via headless Chromium."""

    def __init__(self, config: Config, browser: Browser | None = None) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = browser
        self._owns_browser = browser is None

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._config.browser_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        log.info("TurnstileSolver browser started")

    async def stop(self) -> None:
        if self._owns_browser:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        log.info("TurnstileSolver stopped")

    async def solve(self, params: dict[str, Any]) -> dict[str, Any]:
        website_url = params["websiteURL"]
        website_key = params["websiteKey"]

        last_error: Exception | None = None
        for attempt in range(self._config.captcha_retries):
            try:
                token = await self._solve_once(website_url, website_key)
                return {"token": token}
            except Exception as exc:
                last_error = exc
                log.warning(
                    "Turnstile attempt %d/%d failed: %s",
                    attempt + 1,
                    self._config.captcha_retries,
                    exc,
                )
                if attempt < self._config.captcha_retries - 1:
                    await asyncio.sleep(2)

        raise RuntimeError(
            f"Turnstile failed after {self._config.captcha_retries} attempts: {last_error}"
        )

    async def _solve_once(self, website_url: str, website_key: str) -> str:
        assert self._browser is not None

        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = await context.new_page()
        await page.add_init_script(_STEALTH_JS)

        try:
            timeout_ms = self._config.browser_timeout * 1000
            await page.goto(website_url, wait_until="networkidle", timeout=timeout_ms)

            await page.mouse.move(400, 300)
            await asyncio.sleep(1)

            # Try clicking the Turnstile checkbox
            try:
                iframe_element = await self._checkbox_frame(page, website_key)
                checkbox = iframe_element.locator(
                    'input[type="checkbox"], .ctp-checkbox-label, label'
                )
                await checkbox.click(timeout=8_000)
            except Exception:
                log.info("No Turnstile checkbox found, waiting for auto-solve")

            # Wait for the token to appear
            for _ in range(15):
                await asyncio.sleep(2)
                token = await page.evaluate(_EXTRACT_TURNSTILE_TOKEN_JS)
                if token:
                    log.info("Got Turnstile token (len=%d)", len(token))
                    return token

            raise RuntimeError("Turnstile token not obtained within timeout")
        finally:
            await context.close()

    async def _checkbox_frame(self, page: Any, website_key: str) -> Any:
        """Return the Turnstile frame locator scoped by websiteKey when present."""
        if website_key:
            scoped = f'[data-sitekey="{website_key}"] iframe'
            if await page.locator(scoped).count() > 0:
                return page.frame_locator(scoped)
        return page.frame_locator(
            'iframe[src*="challenges.cloudflare.com"], iframe[src*="turnstile"]'
        )

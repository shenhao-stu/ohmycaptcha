"""HCaptcha solver using Playwright browser automation.

Supports HCaptchaTaskProxyless task type.
Visits the target page, interacts with the hCaptcha widget, and extracts the response token.
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

_EXTRACT_HCAPTCHA_TOKEN_JS = """
(sitekey) => {
    const scope = sitekey
        ? Array.from(document.querySelectorAll('[data-sitekey]'))
            .find((el) => el.getAttribute('data-sitekey') === sitekey) || null
        : null;
    const root = scope || document;
    const textarea = root.querySelector('[name="h-captcha-response"]')
        || root.querySelector('[name="g-recaptcha-response"]');
    if (textarea && textarea.value && textarea.value.length > 20) {
        return textarea.value;
    }
    if (!scope && window.hcaptcha && typeof window.hcaptcha.getResponse === 'function') {
        const resp = window.hcaptcha.getResponse();
        if (resp && resp.length > 20) return resp;
    }
    return null;
}
"""


class HCaptchaSolver:
    """Solves HCaptchaTaskProxyless tasks via headless Chromium."""

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
        log.info("HCaptchaSolver browser started")

    async def stop(self) -> None:
        if self._owns_browser:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        log.info("HCaptchaSolver stopped")

    async def solve(self, params: dict[str, Any]) -> dict[str, Any]:
        website_url = params["websiteURL"]
        website_key = params["websiteKey"]

        last_error: Exception | None = None
        for attempt in range(self._config.captcha_retries):
            try:
                token = await self._solve_once(website_url, website_key)
                return {"gRecaptchaResponse": token}
            except Exception as exc:
                last_error = exc
                log.warning(
                    "HCaptcha attempt %d/%d failed: %s",
                    attempt + 1,
                    self._config.captcha_retries,
                    exc,
                )
                if attempt < self._config.captcha_retries - 1:
                    await asyncio.sleep(2)

        raise RuntimeError(
            f"HCaptcha failed after {self._config.captcha_retries} attempts: {last_error}"
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

            # Click only the checkbox iframe — scope by websiteKey when available
            iframe_element = await self._checkbox_frame(page, website_key)
            checkbox = iframe_element.locator("#checkbox")
            await checkbox.click(timeout=10_000)

            # Wait for token — may require challenge completion; poll up to 30s
            for _ in range(6):
                await asyncio.sleep(5)
                token = await page.evaluate(_EXTRACT_HCAPTCHA_TOKEN_JS, website_key)
                if isinstance(token, str) and len(token) > 20:
                    break
            else:
                token = None

            if not isinstance(token, str) or len(token) < 20:
                raise RuntimeError(f"Invalid hCaptcha token: {token!r}")

            log.info("Got hCaptcha token (len=%d)", len(token))
            return token
        finally:
            await context.close()

    async def _checkbox_frame(self, page: Any, website_key: str) -> Any:
        """Return the hCaptcha checkbox frame locator scoped by websiteKey when present."""
        base_selector = (
            'iframe[title="Widget containing checkbox for hCaptcha security challenge"]'
        )
        if website_key:
            scoped = f'[data-sitekey="{website_key}"] {base_selector}'
            if await page.locator(scoped).count() > 0:
                return page.frame_locator(scoped)
        return page.frame_locator(base_selector)

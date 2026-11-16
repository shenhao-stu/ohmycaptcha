"""reCAPTCHA v2 solver using Playwright browser automation.

Supports NoCaptchaTaskProxyless, RecaptchaV2TaskProxyless,
and RecaptchaV2EnterpriseTaskProxyless task types.

Strategy:
  1. Visit the target page with a realistic browser context.
  2. Click the reCAPTCHA checkbox.
  3. If the challenge dialog appears (bot detected), switch to the audio
     challenge, download the audio file, transcribe it via the configured
     speech-to-text model, and submit the text.
  4. Extract the gRecaptchaResponse token.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from playwright.async_api import Browser, Playwright, async_playwright

from ..core.config import Config

log = logging.getLogger(__name__)

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
"""

_EXTRACT_TOKEN_JS = """
() => {
    const textarea = document.querySelector('#g-recaptcha-response')
        || document.querySelector('[name="g-recaptcha-response"]');
    if (textarea && textarea.value && textarea.value.length > 20) {
        return textarea.value;
    }
    const gr = window.grecaptcha?.enterprise || window.grecaptcha;
    if (gr && typeof gr.getResponse === 'function') {
        const resp = gr.getResponse();
        if (resp && resp.length > 20) return resp;
    }
    return null;
}
"""


class RecaptchaV2Solver:
    """Solves reCAPTCHA v2 tasks via headless Chromium with checkbox clicking.

    Falls back to the audio challenge path when Google presents a visual
    challenge to the headless browser.
    """

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
        log.info("RecaptchaV2Solver browser started")

    async def stop(self) -> None:
        if self._owns_browser:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        log.info("RecaptchaV2Solver stopped")

    async def solve(self, params: dict[str, Any]) -> dict[str, Any]:
        website_url = params["websiteURL"]
        website_key = params["websiteKey"]
        is_invisible = params.get("isInvisible", False)

        last_error: Exception | None = None
        for attempt in range(self._config.captcha_retries):
            try:
                token = await self._solve_once(website_url, website_key, is_invisible)
                return {"gRecaptchaResponse": token}
            except Exception as exc:
                last_error = exc
                log.warning(
                    "reCAPTCHA v2 attempt %d/%d failed: %s",
                    attempt + 1,
                    self._config.captcha_retries,
                    exc,
                )
                if attempt < self._config.captcha_retries - 1:
                    await asyncio.sleep(2)

        raise RuntimeError(
            f"reCAPTCHA v2 failed after {self._config.captcha_retries} attempts: {last_error}"
        )

    async def _solve_once(
        self, website_url: str, website_key: str, is_invisible: bool
    ) -> str:
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
            await asyncio.sleep(0.5)

            if is_invisible:
                token = await page.evaluate(
                    """
                    ([key]) => new Promise((resolve, reject) => {
                        const gr = window.grecaptcha?.enterprise || window.grecaptcha;
                        if (!gr) { reject(new Error('grecaptcha not found')); return; }
                        gr.ready(() => {
                            gr.execute(key).then(resolve).catch(reject);
                        });
                    })
                    """,
                    [website_key],
                )
            else:
                token = await self._solve_checkbox(page, website_key)

            if not isinstance(token, str) or len(token) < 20:
                raise RuntimeError(f"Invalid reCAPTCHA v2 token: {token!r}")

            log.info("Got reCAPTCHA v2 token (len=%d)", len(token))
            return token
        finally:
            await context.close()

    async def _checkbox_frame(self, page: Any, website_key: str = "") -> Any:
        """Return the reCAPTCHA checkbox frame locator scoped by websiteKey when present."""
        base_selector = 'iframe[title="reCAPTCHA"]'
        if website_key:
            scoped = f'[data-sitekey="{website_key}"] {base_selector}'
            if await page.locator(scoped).count() > 0:
                return page.frame_locator(scoped).first
        return page.frame_locator(base_selector).first

    async def _solve_checkbox(self, page: Any, website_key: str = "") -> str | None:
        """Click the reCAPTCHA checkbox. If a visual challenge appears, try audio path."""
        checkbox_frame = await self._checkbox_frame(page, website_key)
        checkbox = checkbox_frame.locator("#recaptcha-anchor")
        await checkbox.click(timeout=10_000)
        await asyncio.sleep(2)

        # Check if token was issued immediately (low-risk sessions)
        token = await page.evaluate(_EXTRACT_TOKEN_JS)
        if isinstance(token, str) and len(token) > 20:
            return token

        # Challenge dialog appeared — try audio challenge path
        log.info("reCAPTCHA challenge detected, attempting audio path")
        try:
            token = await self._solve_audio_challenge(page)
        except Exception as exc:
            log.warning("Audio challenge path failed: %s", exc)
            token = None

        return token

    async def _solve_audio_challenge(self, page: Any) -> str | None:
        """Click the audio button in the bframe and transcribe the audio."""
        # The challenge bframe has title containing "recaptcha challenge"
        bframe = page.frame_locator('iframe[title*="recaptcha challenge"]')

        # Click the audio challenge button
        audio_btn = bframe.locator("#recaptcha-audio-button")
        await audio_btn.click(timeout=8_000)

        # Wait for the audio challenge iframe to load its content
        await asyncio.sleep(3)

        # After clicking audio, a new bframe is rendered with the audio player
        bframe = page.frame_locator('iframe[title*="recaptcha challenge"]')

        # Get the audio source URL — try multiple selectors
        audio_src = None
        for selector in [
            ".rc-audiochallenge-tdownload-link",
            "a[href*='.mp3']",
            "audio source",
        ]:
            try:
                element = bframe.locator(selector).first
                audio_src = await element.get_attribute("href", timeout=5_000) or await element.get_attribute("src", timeout=1_000)
                if audio_src:
                    break
            except Exception:
                continue

        if not audio_src:
            raise RuntimeError("Could not find audio challenge download link")

        # Download the audio file
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(audio_src)
            resp.raise_for_status()
            audio_bytes = resp.content

        # Transcribe via the vision/language model (base64 audio → text)
        transcript = await self._transcribe_audio(audio_bytes)
        log.info("Audio transcribed: %r", transcript[:40] if transcript else None)

        if not transcript:
            raise RuntimeError("Audio transcription returned empty result")

        # Submit the transcript
        audio_input = bframe.locator("#audio-response")
        await audio_input.fill(transcript.strip().lower())
        verify_btn = bframe.locator("#recaptcha-verify-button")
        await verify_btn.click(timeout=8_000)
        await asyncio.sleep(2)

        return await page.evaluate(_EXTRACT_TOKEN_JS)

    async def _transcribe_audio(self, audio_bytes: bytes) -> str | None:
        """Send audio bytes to the OpenAI-compatible audio transcription endpoint."""
        import base64

        audio_b64 = base64.b64encode(audio_bytes).decode()
        payload = {
            "model": self._config.captcha_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This is a reCAPTCHA audio challenge. "
                                "The audio contains spoken digits or words. "
                                "Transcribe exactly what is spoken, digits only, "
                                "separated by spaces. Reply with only the transcription."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:audio/mp3;base64,{audio_b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 50,
            "temperature": 0,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._config.captcha_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._config.captcha_api_key}"},
                json=payload,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Transcription API error {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

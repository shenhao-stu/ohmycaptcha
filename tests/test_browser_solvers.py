"""Unit tests for browser solver websiteKey scoping and Enterprise v3 handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Config
from src.services.hcaptcha import _EXTRACT_HCAPTCHA_TOKEN_JS, HCaptchaSolver
from src.services.recaptcha_v2 import _EXTRACT_TOKEN_JS, RecaptchaV2Solver
from src.services.recaptcha_v3 import _EXECUTE_JS, RecaptchaV3Solver
from src.services.turnstile import _EXTRACT_TURNSTILE_TOKEN_JS, TurnstileSolver


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _make_config() -> Config:
    return Config(
        server_host="127.0.0.1",
        server_port=8000,
        client_key=None,
        cloud_base_url="https://example.com/v1",
        cloud_api_key="test-key",
        cloud_model="gpt-5.4",
        local_base_url="http://localhost:30000/v1",
        local_api_key="EMPTY",
        local_model="Qwen/Qwen3.5-2B",
        captcha_retries=1,
        captcha_timeout=30,
        browser_headless=True,
        browser_timeout=30,
    )


def test_execute_js_supports_enterprise_script() -> None:
    """_EXECUTE_JS must support enterprise.js injection when isEnterprise is true."""
    assert "enterprise.js?render=" in _EXECUTE_JS


def test_token_extractors_scope_by_sitekey() -> None:
    """Token extraction JS helpers must accept sitekey and scope to [data-sitekey]."""
    for script in (
        _EXTRACT_HCAPTCHA_TOKEN_JS,
        _EXTRACT_TOKEN_JS,
        _EXTRACT_TURNSTILE_TOKEN_JS,
    ):
        assert "(sitekey)" in script
        assert "data-sitekey" in script


@pytest.mark.anyio
async def test_recaptcha_v3_passes_enterprise_flag() -> None:
    """RecaptchaV3Solver passes is_enterprise=True only for Enterprise task types."""
    solver = RecaptchaV3Solver(_make_config())
    with patch.object(
        solver, "_solve_once", new=AsyncMock(return_value="tok-" + "x" * 30)
    ) as mock_once:
        await solver.solve(
            {
                "type": "RecaptchaV3EnterpriseTask",
                "websiteURL": "https://example.com",
                "websiteKey": "site-key",
            }
        )
        assert mock_once.call_args.kwargs.get("is_enterprise") is True

        await solver.solve(
            {
                "type": "RecaptchaV3TaskProxyless",
                "websiteURL": "https://example.com",
                "websiteKey": "site-key",
            }
        )
        assert mock_once.call_args.kwargs.get("is_enterprise") is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("solver_cls", "expected_scoped_prefix"),
    [
        (HCaptchaSolver, '[data-sitekey="my-key"] iframe'),
        (TurnstileSolver, '[data-sitekey="my-key"] iframe'),
        (RecaptchaV2Solver, '[data-sitekey="my-key"] iframe'),
    ],
)
async def test_browser_solvers_scope_by_website_key(
    solver_cls: type[HCaptchaSolver | TurnstileSolver | RecaptchaV2Solver],
    expected_scoped_prefix: str,
) -> None:
    """Solvers scope to [data-sitekey=...] when present, else fall back."""
    solver = solver_cls(_make_config())

    scoped_locator = MagicMock()
    scoped_locator.count = AsyncMock(return_value=1)
    page = MagicMock()
    page.locator.return_value = scoped_locator
    page.frame_locator.return_value = MagicMock()

    await solver._checkbox_frame(page, "my-key")
    called_selector = page.frame_locator.call_args.args[0]
    assert called_selector.startswith(expected_scoped_prefix)

    # Fallback when data-sitekey container is absent
    scoped_locator.count = AsyncMock(return_value=0)
    page.frame_locator.reset_mock()
    await solver._checkbox_frame(page, "my-key")
    fallback_selector = page.frame_locator.call_args.args[0]
    assert not fallback_selector.startswith('[data-sitekey="my-key"]')

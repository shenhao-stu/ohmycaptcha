"""Unit tests verifying CAPTCHA_TIMEOUT is propagated to model/HTTP clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Config
from src.services.classification import ClassificationSolver
from src.services.recaptcha_v2 import RecaptchaV2Solver
from src.services.recognition import CaptchaRecognizer


def _make_config(timeout: int = 42) -> Config:
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
        captcha_timeout=timeout,
        browser_headless=True,
        browser_timeout=30,
    )


def test_recognition_passes_captcha_timeout() -> None:
    """CaptchaRecognizer must initialize AsyncOpenAI with config.captcha_timeout."""
    with patch("src.services.recognition.AsyncOpenAI") as mock_openai:
        CaptchaRecognizer(_make_config(42))
        assert mock_openai.call_args.kwargs.get("timeout") == 42


def test_classification_passes_captcha_timeout() -> None:
    """ClassificationSolver must initialize AsyncOpenAI with config.captcha_timeout."""
    with patch("src.services.classification.AsyncOpenAI") as mock_openai:
        ClassificationSolver(_make_config(42))
        assert mock_openai.call_args.kwargs.get("timeout") == 42


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_recaptcha_v2_passes_captcha_timeout() -> None:
    """RecaptchaV2Solver._transcribe_audio must pass config.captcha_timeout to httpx."""
    solver = RecaptchaV2Solver(_make_config(42))
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "5 6"}}]
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch(
        "src.services.recaptcha_v2.httpx.AsyncClient", return_value=mock_client
    ) as mock_httpx:
        await solver._transcribe_audio(b"audio")
        assert mock_httpx.call_args.kwargs.get("timeout") == 42

"""Unit tests for RecaptchaV2Solver audio transcription."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Config
from src.services.recaptcha_v2 import RecaptchaV2Solver


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
        captcha_timeout=25,
        browser_headless=True,
        browser_timeout=30,
    )


@pytest.mark.anyio
async def test_transcribe_audio_uses_input_audio_content_block() -> None:
    """Audio transcription must send MP3 bytes using the OpenAI input_audio block."""
    solver = RecaptchaV2Solver(_make_config())
    audio_bytes = b"fake-mp3-data"
    captured: dict[str, Any] = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "1 2 3 4"}}]
    }

    async def fake_post(url: str, **kwargs: Any) -> MagicMock:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return mock_response

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=fake_post)

    with patch("src.services.recaptcha_v2.httpx.AsyncClient", return_value=mock_client):
        transcript = await solver._transcribe_audio(audio_bytes)

    assert transcript == "1 2 3 4"
    content = captured["json"]["messages"][0]["content"]
    audio_blocks = [item for item in content if item.get("type") == "input_audio"]
    assert len(audio_blocks) == 1
    assert audio_blocks[0]["input_audio"] == {
        "data": base64.b64encode(audio_bytes).decode(),
        "format": "mp3",
    }

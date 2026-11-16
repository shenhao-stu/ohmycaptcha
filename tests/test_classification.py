"""Unit tests for ClassificationSolver."""

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from src.core.config import Config
from src.services.classification import ClassificationSolver


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
        captcha_timeout=15,
        browser_headless=True,
        browser_timeout=30,
    )


def _sample_b64_png() -> str:
    img = Image.new("RGB", (8, 8), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.mark.anyio
async def test_hcaptcha_queries_without_question_sends_string_text() -> None:
    """When question is omitted, queries must not be passed as a list to text content."""
    solver = ClassificationSolver(_make_config())
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer": [0, 2]}'))]
    )
    mock_create = AsyncMock(return_value=fake_response)
    solver._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )

    b64 = _sample_b64_png()
    result = await solver.solve(
        {"type": "HCaptchaClassification", "queries": [b64, b64, b64]}
    )

    mock_create.assert_awaited_once()
    messages = mock_create.call_args.kwargs["messages"]
    text_blocks = [
        item for item in messages[1]["content"] if item.get("type") == "text"
    ]
    assert len(text_blocks) == 1
    assert isinstance(text_blocks[0]["text"], str)
    assert result["objects"] == [0, 2]
    assert result["answer"] == [0, 2]


@pytest.mark.anyio
async def test_hcaptcha_boolean_answer_preserves_boolean() -> None:
    """Single-image boolean HCaptcha answers remain boolean without objects."""
    solver = ClassificationSolver(_make_config())
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"answer": True})))]
    )
    solver._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=fake_response))
        )
    )

    result = await solver.solve(
        {
            "type": "HCaptchaClassification",
            "image": _sample_b64_png(),
            "question": "Is this a bicycle?",
        }
    )

    assert result == {"answer": True}

"""Tests for the YesCaptcha-compatible captcha solver API."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    _ = sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402


def _load_app(*, client_key: str | None = None) -> TestClient:
    """Reload modules with fresh env vars and return a test client."""
    os.environ.setdefault("CLIENT_KEY", "test-key")
    os.environ.setdefault("CAPTCHA_BASE_URL", "https://example.com/v1")
    os.environ.setdefault("CAPTCHA_API_KEY", "test-key")
    os.environ.setdefault("CAPTCHA_MODEL", "gpt-5.4")
    os.environ.setdefault("CAPTCHA_MULTIMODAL_MODEL", "qwen3.5-2b")
    os.environ.setdefault("BROWSER_HEADLESS", "true")
    if client_key is not None:
        os.environ["CLIENT_KEY"] = client_key

    config_mod = importlib.import_module("src.core.config")
    routes_mod = importlib.import_module("src.api.routes")
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    main_mod = importlib.import_module("src.main")

    _ = importlib.reload(config_mod)
    _ = importlib.reload(task_mgr_mod)
    _ = importlib.reload(routes_mod)
    main_mod = importlib.reload(main_mod)

    return TestClient(main_mod.app)


ALL_TASK_TYPES = [
    "RecaptchaV3TaskProxyless",
    "RecaptchaV3TaskProxylessM1",
    "RecaptchaV3TaskProxylessM1S7",
    "RecaptchaV3TaskProxylessM1S9",
    "RecaptchaV3EnterpriseTask",
    "RecaptchaV3EnterpriseTaskM1",
    "NoCaptchaTaskProxyless",
    "RecaptchaV2TaskProxyless",
    "RecaptchaV2EnterpriseTaskProxyless",
    "HCaptchaTaskProxyless",
    "TurnstileTaskProxyless",
    "TurnstileTaskProxylessM1",
    "ImageToTextTask",
    "ImageToTextTaskMuggle",
    "ImageToTextTaskM1",
    "HCaptchaClassification",
    "ReCaptchaV2Classification",
    "FunCaptchaClassification",
    "AwsClassification",
]


def test_health_endpoint() -> None:
    client = _load_app()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "cloud_model" in body
    assert "local_model" in body


def test_root_endpoint() -> None:
    client = _load_app()
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "captcha-solver"
    assert body["version"] == "3.0.0"
    assert "createTask" in body["endpoints"]
    assert isinstance(body["supported_task_types"], list)


def test_root_endpoint_reports_all_supported_types() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    for task_type in ALL_TASK_TYPES:
        mgr.register_solver(task_type, AsyncMock())
    response = client.get("/")
    body = response.json()
    assert set(body["supported_task_types"]) == set(ALL_TASK_TYPES)


def test_get_balance() -> None:
    client = _load_app()
    response = client.post("/getBalance", json={"clientKey": "test-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["errorId"] == 0
    assert body["balance"] > 0


def test_get_balance_requires_client_key() -> None:
    client = _load_app(client_key="secret")
    bad = client.post("/getBalance", json={"clientKey": "wrong"})
    good = client.post("/getBalance", json={"clientKey": "secret"})
    assert bad.json()["errorId"] == 1
    assert good.json()["errorId"] == 0


def test_create_task_unsupported_type() -> None:
    client = _load_app()
    response = client.post(
        "/createTask",
        json={
            "clientKey": "test-key",
            "task": {"type": "UnsupportedType", "websiteURL": "https://example.com"},
        },
    )
    body = response.json()
    assert body["errorId"] == 1
    assert body["errorCode"] == "ERROR_TASK_NOT_SUPPORTED"


def test_create_task_missing_fields_recaptcha_v3() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mgr.register_solver("RecaptchaV3TaskProxyless", AsyncMock())
    try:
        response = client.post(
            "/createTask",
            json={"clientKey": "test-key", "task": {"type": "RecaptchaV3TaskProxyless"}},
        )
        body = response.json()
        assert body["errorId"] == 1
        assert body["errorCode"] == "ERROR_TASK_PROPERTY_EMPTY"
    finally:
        mgr._solvers.pop("RecaptchaV3TaskProxyless", None)


def test_create_task_missing_fields_recaptcha_v2() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mgr.register_solver("NoCaptchaTaskProxyless", AsyncMock())
    try:
        response = client.post(
            "/createTask",
            json={"clientKey": "test-key", "task": {"type": "NoCaptchaTaskProxyless"}},
        )
        body = response.json()
        assert body["errorId"] == 1
        assert body["errorCode"] == "ERROR_TASK_PROPERTY_EMPTY"
    finally:
        mgr._solvers.pop("NoCaptchaTaskProxyless", None)


def test_create_task_missing_fields_hcaptcha() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mgr.register_solver("HCaptchaTaskProxyless", AsyncMock())
    try:
        response = client.post(
            "/createTask",
            json={"clientKey": "test-key", "task": {"type": "HCaptchaTaskProxyless"}},
        )
        body = response.json()
        assert body["errorId"] == 1
        assert body["errorCode"] == "ERROR_TASK_PROPERTY_EMPTY"
    finally:
        mgr._solvers.pop("HCaptchaTaskProxyless", None)


def test_create_task_missing_fields_turnstile() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mgr.register_solver("TurnstileTaskProxyless", AsyncMock())
    try:
        response = client.post(
            "/createTask",
            json={"clientKey": "test-key", "task": {"type": "TurnstileTaskProxyless"}},
        )
        body = response.json()
        assert body["errorId"] == 1
        assert body["errorCode"] == "ERROR_TASK_PROPERTY_EMPTY"
    finally:
        mgr._solvers.pop("TurnstileTaskProxyless", None)


def test_create_task_missing_fields_image() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mgr.register_solver("ImageToTextTask", AsyncMock())
    try:
        response = client.post(
            "/createTask",
            json={"clientKey": "test-key", "task": {"type": "ImageToTextTask"}},
        )
        body = response.json()
        assert body["errorId"] == 1
        assert body["errorCode"] == "ERROR_TASK_PROPERTY_EMPTY"
    finally:
        mgr._solvers.pop("ImageToTextTask", None)


def test_create_task_missing_fields_classification() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mgr.register_solver("HCaptchaClassification", AsyncMock())
    try:
        response = client.post(
            "/createTask",
            json={"clientKey": "test-key", "task": {"type": "HCaptchaClassification"}},
        )
        body = response.json()
        assert body["errorId"] == 1
        assert body["errorCode"] == "ERROR_TASK_PROPERTY_EMPTY"
    finally:
        mgr._solvers.pop("HCaptchaClassification", None)


def test_create_task_invalid_client_key() -> None:
    client = _load_app(client_key="correct-key")
    response = client.post(
        "/createTask",
        json={
            "clientKey": "wrong-key",
            "task": {
                "type": "RecaptchaV3TaskProxyless",
                "websiteURL": "https://example.com",
                "websiteKey": "key123",
            },
        },
    )
    body = response.json()
    assert body["errorId"] == 1
    assert body["errorCode"] == "ERROR_KEY_DOES_NOT_EXIST"


def test_get_task_result_not_found() -> None:
    client = _load_app()
    response = client.post(
        "/getTaskResult",
        json={"clientKey": "test-key", "taskId": "nonexistent-id"},
    )
    body = response.json()
    assert body["errorId"] == 1
    assert body["errorCode"] == "ERROR_NO_SUCH_CAPCHA_ID"


def test_create_recaptcha_v3_task_accepted() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mock_solver = AsyncMock(return_value={"gRecaptchaResponse": "tok"})
    mock_solver.solve = mock_solver
    mgr.register_solver("RecaptchaV3TaskProxyless", mock_solver)
    try:
        resp = client.post(
            "/createTask",
            json={
                "clientKey": "test-key",
                "task": {
                    "type": "RecaptchaV3TaskProxyless",
                    "websiteURL": "https://example.com",
                    "websiteKey": "test-key",
                },
            },
        )
        body = resp.json()
        assert body["errorId"] == 0
        assert body["taskId"] is not None
    finally:
        mgr._solvers.pop("RecaptchaV3TaskProxyless", None)


def test_create_turnstile_task_accepted() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mock_solver = AsyncMock(return_value={"token": "cf-tok"})
    mock_solver.solve = mock_solver
    mgr.register_solver("TurnstileTaskProxyless", mock_solver)
    try:
        resp = client.post(
            "/createTask",
            json={
                "clientKey": "test-key",
                "task": {
                    "type": "TurnstileTaskProxyless",
                    "websiteURL": "https://example.com",
                    "websiteKey": "1x000",
                },
            },
        )
        body = resp.json()
        assert body["errorId"] == 0
        assert body["taskId"] is not None
    finally:
        mgr._solvers.pop("TurnstileTaskProxyless", None)


def test_create_classification_task_accepted() -> None:
    client = _load_app()
    task_mgr_mod = importlib.import_module("src.services.task_manager")
    mgr = task_mgr_mod.task_manager
    mock_solver = AsyncMock(return_value={"objects": [0, 3]})
    mock_solver.solve = mock_solver
    mgr.register_solver("ReCaptchaV2Classification", mock_solver)
    try:
        resp = client.post(
            "/createTask",
            json={
                "clientKey": "test-key",
                "task": {
                    "type": "ReCaptchaV2Classification",
                    "image": "aGVsbG8=",
                    "question": "Select traffic lights",
                },
            },
        )
        body = resp.json()
        assert body["errorId"] == 0
        assert body["taskId"] is not None
    finally:
        mgr._solvers.pop("ReCaptchaV2Classification", None)

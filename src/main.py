"""Robotax captcha service: YesCaptcha-compatible API with explicit registration."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .api.routes import router
from .core.config import Config, config
from .services.classification import ClassificationSolver
from .services.hcaptcha import HCaptchaSolver
from .services.recaptcha_v2 import RecaptchaV2Solver
from .services.recaptcha_v3 import RecaptchaV3Solver
from .services.recognition import CaptchaRecognizer
from .services.task_manager import task_manager
from .services.turnstile import TurnstileSolver

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

_TASK_TYPES: dict[str, tuple[str, ...]] = {
    "v3": (
        "RecaptchaV3TaskProxyless",
        "RecaptchaV3TaskProxylessM1",
        "RecaptchaV3TaskProxylessM1S7",
        "RecaptchaV3TaskProxylessM1S9",
        "RecaptchaV3EnterpriseTask",
        "RecaptchaV3EnterpriseTaskM1",
    ),
    "v2": (
        "NoCaptchaTaskProxyless",
        "RecaptchaV2TaskProxyless",
        "RecaptchaV2EnterpriseTaskProxyless",
    ),
    "hcaptcha": ("HCaptchaTaskProxyless",),
    "turnstile": ("TurnstileTaskProxyless", "TurnstileTaskProxylessM1"),
    "classification": (
        "HCaptchaClassification",
        "ReCaptchaV2Classification",
        "FunCaptchaClassification",
        "AwsClassification",
    ),
    "image": ("ImageToTextTask", "ImageToTextTaskMuggle", "ImageToTextTaskM1"),
}


def register_solvers(settings: Config) -> list[Any]:
    """Register all solvers explicitly; return browser solvers needing startup."""
    v3 = RecaptchaV3Solver(settings)
    v2 = RecaptchaV2Solver(settings)
    hcaptcha = HCaptchaSolver(settings)
    turnstile = TurnstileSolver(settings)
    for group, solver in (
        ("v3", v3),
        ("v2", v2),
        ("hcaptcha", hcaptcha),
        ("turnstile", turnstile),
        ("classification", ClassificationSolver(settings)),
        ("image", CaptchaRecognizer(settings)),
    ):
        for task_type in _TASK_TYPES[group]:
            task_manager.register_solver(task_type, solver)
    return [v3, v2, hcaptcha, turnstile]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    solvers = register_solvers(config)
    for solver in solvers:
        await solver.start()
    await task_manager.start()
    yield
    await task_manager.stop()
    for solver in solvers:
        await solver.stop()


app = FastAPI(
    title="Robotax Captcha Solver",
    version="0.1.0",
    description="YesCaptcha-compatible captcha solving service for Robotax.",
    lifespan=lifespan,
)
app.include_router(router)
register_solvers(config)


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    """Report registered solvers and model configuration, never secret values."""
    return {
        "status": "ok",
        "supported_task_types": task_manager.supported_types(),
        "browser_headless": config.browser_headless,
        "model_configured": bool(config.local_base_url and config.local_model),
        "client_key_configured": bool(config.client_key),
    }


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "robotax-captcha",
        "version": app.version,
        "endpoints": ["/createTask", "/getTaskResult", "/getBalance", "/api/v1/health"],
    }

"""Environment-driven application configuration.

Two model backends are supported:

  Cloud model  — a remote OpenAI-compatible API (e.g. gpt-5.4 via a hosted
                 endpoint).  Used as the powerful multimodal backbone for
                 tasks like audio transcription.

  Local model  — a self-hosted model served via SGLang, vLLM, or any
                 OpenAI-compatible server (e.g. Qwen3.5-2B on localhost).
                 Used for high-throughput image recognition / classification.

Both backends expose ``/v1/chat/completions``; the only difference is the
base URL, API key, and model name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass



def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


@dataclass(frozen=True)
class Config:
    server_host: str
    server_port: int

    # Auth: YesCaptcha clientKey
    client_key: str | None

    # ── Cloud model (remote API) ──
    cloud_base_url: str
    cloud_api_key: str
    cloud_model: str

    # ── Local model (self-hosted via SGLang / vLLM) ──
    local_base_url: str
    local_api_key: str
    local_model: str

    captcha_retries: int
    captcha_timeout: int

    # Playwright browser
    browser_headless: bool
    browser_timeout: int  # seconds
    browser_proxy_server: str | None

    # ── Convenience aliases (backward-compat) ──

    @property
    def captcha_base_url(self) -> str:
        return self.cloud_base_url

    @property
    def captcha_api_key(self) -> str:
        return self.cloud_api_key

    @property
    def captcha_model(self) -> str:
        return self.cloud_model

    @property
    def captcha_multimodal_model(self) -> str:
        return self.local_model


def load_config() -> Config:
    return Config(
        server_host=os.environ.get("SERVER_HOST", "0.0.0.0"),
        server_port=int(os.environ.get("SERVER_PORT", "8000")),
        client_key=os.environ.get("CLIENT_KEY", "").strip() or None,
        # Cloud model
        cloud_base_url=os.environ.get(
            "CLOUD_BASE_URL",
            os.environ.get("CAPTCHA_BASE_URL", "https://your-openai-compatible-endpoint/v1"),
        ),
        cloud_api_key=os.environ.get(
            "CLOUD_API_KEY",
            os.environ.get("CAPTCHA_API_KEY", ""),
        ),
        cloud_model=os.environ.get(
            "CLOUD_MODEL",
            os.environ.get("CAPTCHA_MODEL", "gpt-5.4"),
        ),
        # Local model
        local_base_url=os.environ.get(
            "LOCAL_BASE_URL",
            os.environ.get("CAPTCHA_BASE_URL", "http://localhost:30000/v1"),
        ),
        local_api_key=os.environ.get(
            "LOCAL_API_KEY",
            os.environ.get("CAPTCHA_API_KEY", "EMPTY"),
        ),
        local_model=os.environ.get(
            "LOCAL_MODEL",
            os.environ.get("CAPTCHA_MULTIMODAL_MODEL", "Qwen/Qwen3.5-2B"),
        ),
        captcha_retries=int(os.environ.get("CAPTCHA_RETRIES", "3")),
        captcha_timeout=int(os.environ.get("CAPTCHA_TIMEOUT", "30")),
        browser_headless=os.environ.get("BROWSER_HEADLESS", "true").strip().lower()
        in {"1", "true", "yes"},
        browser_timeout=int(os.environ.get("BROWSER_TIMEOUT", "30")),
        browser_proxy_server=_first_env(
            "BROWSER_PROXY_SERVER", "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY"
        ),
    )


config = load_config()

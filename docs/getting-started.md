# Getting Started

## Requirements

- Python 3.10+
- Chromium available through Playwright
- Network access to:
  - target sites you want to solve against
  - your configured OpenAI-compatible model endpoint

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
```

## Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `CLIENT_KEY` | Client auth key used as `clientKey` | unset |
| `LOCAL_BASE_URL` | Local OpenAI-compatible inference server (SGLang/vLLM) | `http://localhost:30000/v1` |
| `LOCAL_API_KEY` | Local server API key | `EMPTY` |
| `LOCAL_MODEL` | Local multimodal model | `Qwen/Qwen3.5-2B` |
| `CLOUD_BASE_URL` | Cloud OpenAI-compatible API base URL | `https://your-openai-compatible-endpoint/v1` |
| `CLOUD_API_KEY` | API key for your cloud model provider | unset |
| `CLOUD_MODEL` | Cloud model | `gpt-5.4` |
| `CAPTCHA_RETRIES` | Retry count | `3` |
| `CAPTCHA_TIMEOUT` | Model timeout in seconds | `30` |
| `BROWSER_HEADLESS` | Run Chromium headless | `true` |
| `BROWSER_TIMEOUT` | Browser timeout in seconds | `30` |
| `SERVER_HOST` | Bind host | `0.0.0.0` |
| `SERVER_PORT` | Bind port | `8000` |

> Legacy variables (`CAPTCHA_BASE_URL`, `CAPTCHA_API_KEY`, `CAPTCHA_MODEL`, `CAPTCHA_MULTIMODAL_MODEL`) are supported as fallbacks when `LOCAL_*` / `CLOUD_*` are unset.

## Start the service

```bash
export CLIENT_KEY="your-client-key"
export LOCAL_BASE_URL="http://localhost:30000/v1"
export LOCAL_MODEL="Qwen/Qwen3.5-2B"
export CLOUD_BASE_URL="https://your-openai-compatible-endpoint/v1"
export CLOUD_API_KEY="your-api-key"
export CLOUD_MODEL="gpt-5.4"
python main.py
```

## Verify startup

### Root endpoint

```bash
curl http://localhost:8000/
```

### Health endpoint

```bash
curl http://localhost:8000/api/v1/health
```

The health response should include the registered task types and current runtime model settings.

## Local and self-hosted model support

The image recognition path is built around **OpenAI-compatible APIs**. In practice, this means you can point `CAPTCHA_BASE_URL` at a hosted provider or a self-hosted/local multimodal gateway, as long as it exposes compatible chat-completions semantics and supports image input.

The project intentionally documents this in generic compatibility terms rather than claiming full validation for every provider stack.

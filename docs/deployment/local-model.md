# Local Model Deployment

OhMyCaptcha supports running image recognition and classification tasks on a **locally hosted model** served via [SGLang](https://github.com/sgl-project/sglang), [vLLM](https://github.com/vllm-project/vllm), or any OpenAI-compatible inference server.

This guide covers deploying [Qwen3.5-2B](https://modelscope.cn/models/Qwen/Qwen3.5-2B) locally with SGLang.

## Architecture: Local vs Cloud

OhMyCaptcha uses two model backends:

| Backend | Role | Env vars | Default |
|---------|------|----------|---------|
| **Local model** | Image recognition & classification (high-throughput, self-hosted) | `LOCAL_BASE_URL`, `LOCAL_API_KEY`, `LOCAL_MODEL` | `http://localhost:30000/v1`, `EMPTY`, `Qwen/Qwen3.5-2B` |
| **Cloud model** | Audio transcription & complex reasoning (powerful remote API) | `CLOUD_BASE_URL`, `CLOUD_API_KEY`, `CLOUD_MODEL` | External endpoint, your key, `gpt-5.4` |

```
┌────────────────────────────────────────────────────────────┐
│                      OhMyCaptcha                            │
│                                                            │
│  Browser tasks ──► Playwright (reCAPTCHA, Turnstile)        │
│                                                            │
│  Image tasks ───► Local Model (SGLang / vLLM)               │
│                   └─ Qwen3.5-2B on localhost:30000          │
│                                                            │
│  Audio tasks ───► Cloud Model (remote API)                  │
│                   └─ gpt-5.4 via external endpoint          │
└────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- NVIDIA GPU with CUDA support (recommended: 8GB+ VRAM for Qwen3.5-2B)
- `pip` package manager

## Step 1: Install SGLang

```bash
pip install "sglang[all]>=0.4.6.post1"
```

## Step 2: Launch the model server

### From Hugging Face

```bash
python -m sglang.launch_server \
  --model-path Qwen/Qwen3.5-2B \
  --host 0.0.0.0 \
  --port 30000
```

### From ModelScope (recommended in China)

```bash
export SGLANG_USE_MODELSCOPE=true
python -m sglang.launch_server \
  --model-path Qwen/Qwen3.5-2B \
  --host 0.0.0.0 \
  --port 30000
```

### With multiple GPUs

```bash
python -m sglang.launch_server \
  --model-path Qwen/Qwen3.5-2B \
  --host 0.0.0.0 \
  --port 30000 \
  --tensor-parallel-size 2
```

Once started, the server exposes an OpenAI-compatible API at `http://localhost:30000/v1`.

## Step 3: Verify the model server

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-2B",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 32
  }'
```

You should receive a valid JSON response with model output.

## Step 4: Configure OhMyCaptcha

Set the local model env vars to point at your SGLang server:

```bash
# Local model (self-hosted via SGLang)
export LOCAL_BASE_URL="http://localhost:30000/v1"
export LOCAL_API_KEY="EMPTY"
export LOCAL_MODEL="Qwen/Qwen3.5-2B"

# Cloud model (remote API for audio transcription etc.)
export CLOUD_BASE_URL="https://your-api-endpoint/v1"
export CLOUD_API_KEY="sk-your-key"
export CLOUD_MODEL="gpt-5.4"

# Other config
export CLIENT_KEY="your-client-key"
export BROWSER_HEADLESS=true
```

## Step 5: Start OhMyCaptcha

```bash
python main.py
```

The health endpoint shows both model backends:

```bash
curl http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "supported_task_types": ["RecaptchaV3TaskProxyless", "..."],
  "browser_headless": true,
  "cloud_model": "gpt-5.4",
  "local_model": "Qwen/Qwen3.5-2B"
}
```

## Alternative: vLLM

vLLM can serve the same model with an identical API:

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-2B \
  --host 0.0.0.0 \
  --port 30000
```

No changes to the OhMyCaptcha configuration are needed — both SGLang and vLLM expose `/v1/chat/completions`.

## Backward compatibility

The legacy environment variables (`CAPTCHA_BASE_URL`, `CAPTCHA_API_KEY`, `CAPTCHA_MODEL`, `CAPTCHA_MULTIMODAL_MODEL`) are still supported as fallbacks. If you set `CAPTCHA_BASE_URL` without setting `CLOUD_BASE_URL`, the old value will be used. The new `LOCAL_*` and `CLOUD_*` variables take precedence when set.

## Recommended models

| Model | Size | Use case | VRAM |
|-------|------|----------|------|
| `Qwen/Qwen3.5-2B` | 2B | Image recognition & classification | ~5 GB |
| `Qwen/Qwen3.5-7B` | 7B | Higher accuracy classification | ~15 GB |
| `Qwen/Qwen3.5-2B-FP8` | 2B (quantized) | Lower VRAM requirement | ~3 GB |

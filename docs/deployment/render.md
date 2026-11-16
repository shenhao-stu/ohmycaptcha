# Render Deployment

This guide walks through a clean **Render** deployment for OhMyCaptcha using the Docker files already included in this repository.

## When to choose Render

Render is a good fit when you want:

- managed deployment with a stable public URL
- easy secret management
- a simple Docker-based workflow
- fewer runtime constraints than demo-oriented hosting platforms

## 1. Prepare the repository

This repository already includes the files Render needs:

- `Dockerfile.render`
- `render.yaml`
- `main.py`
- `requirements.txt`
- `src/`

The application listens on port `8000` and also respects the `PORT` environment variable injected by Render.

## 2. Create the Render service

In Render:

1. Create a new **Web Service**.
2. Connect your GitHub repository.
3. Choose **Docker** as the runtime.
4. Point Render at:
   - Dockerfile: `Dockerfile.render`
   - Context: repository root

You can also import the included `render.yaml` blueprint.

## 3. Configure environment variables

### Required secrets

Set these as protected environment variables in the Render dashboard:

- `CLIENT_KEY`
- `CLOUD_API_KEY`

### Recommended variables

- `CLOUD_BASE_URL=https://your-openai-compatible-endpoint/v1`
- `CLOUD_MODEL=gpt-5.4`
- `LOCAL_BASE_URL=https://your-openai-compatible-endpoint/v1`
- `LOCAL_API_KEY=your-api-key`
- `LOCAL_MODEL=Qwen/Qwen3.5-2B`
- `CAPTCHA_RETRIES=3`
- `CAPTCHA_TIMEOUT=30`
- `BROWSER_HEADLESS=true`
- `BROWSER_TIMEOUT=30`

## 4. Trigger the first deploy

After saving the configuration:

- wait for the image build
- confirm Python dependencies install successfully
- confirm Playwright Chromium installation completes successfully
- wait until the service status becomes healthy

## 5. Validate the deployment

Once the Render URL is available, check:

### Root endpoint

```bash
curl https://<your-render-service>.onrender.com/
```

### Health endpoint

```bash
curl https://<your-render-service>.onrender.com/api/v1/health
```

### Create a detector task

```bash
curl -X POST https://<your-render-service>.onrender.com/createTask \
  -H "Content-Type: application/json" \
  -d '{
    "clientKey": "your-client-key",
    "task": {
      "type": "RecaptchaV3TaskProxyless",
      "websiteURL": "https://antcpt.com/score_detector/",
      "websiteKey": "6LcR_okUAAAAAPYrPe-HK_0RULO1aZM15ENyM-Mf",
      "pageAction": "homepage"
    }
  }'
```

## Operational notes

- Render is generally a better fit than lightweight demo platforms for browser automation.
- Browser-based solving can still be sensitive to cold starts, IP quality, and container resource limits.
- If you need stronger control over runtime behavior, move to your own infrastructure.

## Recommended usage

Render is a strong default choice for:

- persistent public deployments
- flow2api integration testing
- low-to-medium production traffic
- quick managed rollout without maintaining your own host

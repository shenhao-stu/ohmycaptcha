# Hugging Face Spaces Deployment

This guide shows how to deploy OhMyCaptcha on **Hugging Face Spaces** using a Docker-based Space.

## When to choose Hugging Face Spaces

Use Hugging Face Spaces when you want:

- a simple public or private demo deployment
- a UI-driven hosting workflow
- easy secret management inside the Space settings
- a Docker-based environment without managing a VPS yourself

## 1. Prepare the repository

Make sure your repository includes:

- `Dockerfile.render`
- `main.py`
- `requirements.txt`
- the `src/` application package

For Hugging Face Spaces, the current Dockerfile can be reused as a starting point because it already installs Python dependencies and Playwright Chromium.

## 2. Create a Docker Space

In Hugging Face:

1. Create a new **Space**.
2. Choose **Docker** as the SDK.
3. Select visibility according to your needs.
4. Connect the Space to this repository or upload the project files.

## 3. Configure secrets and variables

In the Space settings, add the following secrets:

- `CLIENT_KEY`
- `CLOUD_API_KEY`

Add or override variables as needed:

- `CLOUD_BASE_URL`
- `CLOUD_MODEL`
- `LOCAL_BASE_URL`
- `LOCAL_API_KEY`
- `LOCAL_MODEL`
- `BROWSER_HEADLESS=true`
- `BROWSER_TIMEOUT=30`
- `SERVER_PORT=7860`

Hugging Face Spaces typically expose applications on port `7860`, so set `SERVER_PORT=7860`.

## 4. Confirm the startup command

The container should start the app with:

```bash
python main.py
```

The entrypoint already respects environment-based port configuration.

## 5. Wait for the build to finish

After the Space starts building:

- watch the build logs
- confirm dependency installation finishes successfully
- confirm Playwright Chromium installs successfully
- wait for the app to enter the running state

## 6. Validate the deployment

Once the Space is live, verify:

### Root endpoint

```bash
curl https://<your-space-subdomain>.hf.space/
```

### Health endpoint

```bash
curl https://<your-space-subdomain>.hf.space/api/v1/health
```

### Create a detector task

```bash
curl -X POST https://<your-space-subdomain>.hf.space/createTask \
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

- Hugging Face Spaces are convenient, but cold starts and resource limits can affect Playwright-based workloads.
- Browser automation can be more sensitive to shared-hosting environments than standard API-only apps.
- If you need stricter runtime control, use Render or your own infrastructure.

## Recommended usage

Hugging Face Spaces is best suited for:

- evaluation
- demos
- low-volume internal usage
- fast public documentation-linked deployment

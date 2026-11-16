"""Image classification solvers for various captcha types.

Supports HCaptchaClassification, ReCaptchaV2Classification,
FunCaptchaClassification, and AwsClassification task types.

All classification tasks send images + question text to an OpenAI-compatible
vision model for analysis and return structured coordinate/index results.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from PIL import Image

from ..core.config import Config

log = logging.getLogger(__name__)

HCAPTCHA_SYSTEM_PROMPT = """\
You are an image classification assistant for HCaptcha challenges.
Given a question and one or more base64-encoded images, determine which images match the question.

Return STRICT JSON only. No markdown, no extra text.

For single-image questions (is this image X?):
{"answer": true}  or  {"answer": false}

For multi-image grid questions (select all images containing X):
{"answer": [0, 2, 5]}
where numbers are 0-indexed positions of matching images.

Rules:
- Return ONLY the JSON object, nothing else.
- Be precise with your classification.
"""

RECAPTCHA_V2_SYSTEM_PROMPT = """\
You are an image classification assistant for reCAPTCHA v2 challenges.
Given a question and a grid image (3x3 or 4x4), identify which cells match the question.

The image cells are numbered 0-8 (3x3) or 0-15 (4x4), left-to-right, top-to-bottom.

Return STRICT JSON only:
{"objects": [0, 3, 6]}
where numbers are 0-indexed positions of matching cells.

Rules:
- Return ONLY the JSON object, nothing else.
- If no cells match, return {"objects": []}.
"""

FUNCAPTCHA_SYSTEM_PROMPT = """\
You are an image classification assistant for FunCaptcha challenges.
Given a question and a grid image (typically 2x3 = 6 cells), identify which cell
is the correct answer.

Cells are numbered 0-5, left-to-right, top-to-bottom.

Return STRICT JSON only:
{"objects": [3]}
where the number is the 0-indexed position of the correct cell.

Rules:
- Return ONLY the JSON object, nothing else.
- Usually only one cell is correct.
"""

AWS_SYSTEM_PROMPT = """\
You are an image classification assistant for AWS CAPTCHA challenges.
Given a question and one or more images, identify the correct answer.

Return STRICT JSON only:
{"objects": [1]}
where the number is the 0-indexed position of the matching image.

Rules:
- Return ONLY the JSON object, nothing else.
"""


class ClassificationSolver:
    """Solves image classification captchas using a vision model."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = AsyncOpenAI(
            base_url=config.local_base_url,
            api_key=config.local_api_key,
        )

    async def solve(self, params: dict[str, Any]) -> dict[str, Any]:
        task_type = params.get("type", "")
        system_prompt = self._get_system_prompt(task_type)
        raw_question = params.get("question")
        raw_queries = params.get("queries")
        # Preserve string-valued `queries` fallback while excluding image lists
        if isinstance(raw_question, str) and raw_question:
            question = raw_question
        elif isinstance(raw_queries, str):
            question = raw_queries
        else:
            question = ""

        # Handle different image field names across task types
        images = self._extract_images(params)
        if not images:
            raise ValueError("No image data provided")

        result = await self._classify(system_prompt, question, images)
        # Expose `objects` alongside `answer` for HCaptcha grid responses
        if (
            task_type == "HCaptchaClassification"
            and isinstance(result.get("answer"), list)
            and "objects" not in result
        ):
            result["objects"] = result["answer"]
        return result

    @staticmethod
    def _get_system_prompt(task_type: str) -> str:
        prompts = {
            "HCaptchaClassification": HCAPTCHA_SYSTEM_PROMPT,
            "ReCaptchaV2Classification": RECAPTCHA_V2_SYSTEM_PROMPT,
            "FunCaptchaClassification": FUNCAPTCHA_SYSTEM_PROMPT,
            "AwsClassification": AWS_SYSTEM_PROMPT,
        }
        return prompts.get(task_type, RECAPTCHA_V2_SYSTEM_PROMPT)

    @staticmethod
    def _extract_images(params: dict[str, Any]) -> list[str]:
        """Extract base64 image(s) from various param formats."""
        images: list[str] = []

        if "image" in params:
            images.append(params["image"])

        if "images" in params:
            imgs = params["images"]
            if isinstance(imgs, list):
                images.extend(imgs)
            elif isinstance(imgs, str):
                images.append(imgs)

        if "body" in params and not images:
            images.append(params["body"])

        # HCaptcha queries format: list of base64 strings
        if "queries" in params and isinstance(params["queries"], list):
            images.extend(params["queries"])

        return images

    @staticmethod
    def _prepare_image(b64_data: str) -> str:
        """Ensure image is properly formatted as a data URL."""
        if b64_data.startswith("data:image"):
            return b64_data
        try:
            img_bytes = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(img_bytes))
            fmt = img.format or "PNG"
            mime = f"image/{fmt.lower()}"
            return f"data:{mime};base64,{b64_data}"
        except Exception:
            return f"data:image/png;base64,{b64_data}"

    async def _classify(
        self, system_prompt: str, question: str, images: list[str]
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = []

        for img_b64 in images:
            data_url = self._prepare_image(img_b64)
            content.append({
                "type": "image_url",
                "image_url": {"url": data_url, "detail": "high"},
            })

        user_text = question if question else "Classify this captcha image."
        content.append({"type": "text", "text": user_text})

        last_error: Exception | None = None
        for attempt in range(self._config.captcha_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._config.captcha_multimodal_model,
                    temperature=0.05,
                    max_tokens=512,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content},
                    ],
                )
                raw = response.choices[0].message.content or ""
                return self._parse_json(raw)
            except Exception as exc:
                last_error = exc
                log.warning("Classification attempt %d failed: %s", attempt + 1, exc)

        raise RuntimeError(
            f"Classification failed after {self._config.captcha_retries} attempts: {last_error}"
        )

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        cleaned = match.group(1) if match else text.strip()
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")
        return data

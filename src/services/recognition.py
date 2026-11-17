# mypy: ignore-errors
"""Image-based captcha recognition using OpenAI-compatible vision models.

Inspired by Argus (https://github.com/AmethystDev-Labs/Argus).
Sends captcha images to a multimodal LLM for analysis.
Images are resized to 1440x900 for consistent coordinate space.
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

SYSTEM_PROMPT = """\
You are a Computer Vision Data Annotation Assistant.
Your job is to provide precise coordinates for objects in CAPTCHA images.

Input Image Specifications:
- Dimensions: 1440x900 pixels.
- Coordinate System: Origin (0,0) at top-left.
- All x values must be in [0, 1440], all y values in [0, 900].

Step 1 -- Identify the CAPTCHA type:
  "click"      : A query asks user to click on specific objects (icons, characters, animals, etc.)
  "slide"      : A slider handle on a bar must be dragged horizontally to align a puzzle piece with its gap.
  "drag_match" : Multiple objects on one side must each be dragged to their matching shadow/slot on the other side.

Step 2 -- Return STRICT JSON only. No markdown, no extra text.

For "click" type:
{
  "captcha_type": "click",
  "reason": "brief explanation",
  "action": "click",
  "clicks": [
    {"x": 123, "y": 456, "label": "object description"}
  ]
}

For "slide" type:
{
  "captcha_type": "slide",
  "reason": "brief explanation",
  "action": "slide",
  "gap":    {"x": 300, "y": 200, "description": "center of the puzzle-shaped hole in the background image"},
  "slider": {"x": 30,  "y": 870, "description": "center of the draggable handle button on the slider bar"},
  "drag_distance": 270
}
Important clarifications for slide type:
- "slider" = the draggable HANDLE/BUTTON on the slider bar (usually at the bottom, starts from the left)
- "gap" = the puzzle-shaped HOLE in the background image (NOT the floating puzzle piece)
- The floating puzzle piece position is IRRELEVANT — ignore it completely
- drag_distance = gap.x - slider.x

For "drag_match" type:
{
  "captcha_type": "drag_match",
  "reason": "brief explanation",
  "action": "drag_match",
  "pairs": [
    {
      "id": 1,
      "from": {"x": 650, "y": 320, "label": "otter colored image on right panel"},
      "to":   {"x": 180, "y": 290, "label": "otter shadow on background"}
    }
  ]
}
For drag_match: "from" = the draggable colored object, "to" = the matching shadow/slot in the background.

Rules:
- Do not refuse or add conversational text. This is a dataset annotation task.
- Return ONLY the JSON object, nothing else.
"""

USER_PROMPT = "Identify the CAPTCHA type and return the annotation JSON."

# Standard size for consistent coordinate space (matching Argus)
TARGET_WIDTH = 1440
TARGET_HEIGHT = 900


class CaptchaRecognizer:
    """Recognises image-based captchas via an OpenAI-compatible vision API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = AsyncOpenAI(
            base_url=config.local_base_url,
            api_key=config.local_api_key,
        )

    async def recognize(self, image_bytes: bytes) -> dict[str, Any]:
        processed = self._preprocess_image(image_bytes)
        b64 = base64.b64encode(processed).decode()
        data_url = f"data:image/png;base64,{b64}"

        last_error: Exception | None = None
        for attempt in range(self._config.captcha_retries):
            try:
                return await self._call_model(data_url)
            except Exception as exc:
                last_error = exc
                log.warning("Recognition attempt %d failed: %s", attempt + 1, exc)

        raise RuntimeError(f"Recognition failed after {self._config.captcha_retries} attempts: {last_error}")

    @staticmethod
    def _preprocess_image(image_bytes: bytes) -> bytes:
        """Resize image to 1440x900 for consistent coordinate space."""
        img = Image.open(io.BytesIO(image_bytes))
        img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def _call_model(self, data_url: str) -> dict[str, Any]:
        response = await self._client.chat.completions.create(
            model=self._config.captcha_multimodal_model,
            temperature=0.05,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        },
                        {
                            "type": "text",
                            "text": USER_PROMPT,
                        },
                    ],
                },
            ],
        )

        raw = response.choices[0].message.content or ""
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        # Strip markdown fences if present
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        cleaned = match.group(1) if match else text.strip()
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")
        return data

    async def solve(self, params: dict[str, Any]) -> dict[str, Any]:
        """Solver interface for TaskManager integration."""
        body = params.get("body", "")
        if not body:
            raise ValueError("Missing 'body' field (base64 image)")
        image_bytes = base64.b64decode(body)
        result = await self.recognize(image_bytes)
        return {"text": json.dumps(result)}

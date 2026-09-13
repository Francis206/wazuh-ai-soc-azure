"""HTTP client for the inference server (src/llm/inference/server.py),
used by src/soc_automation so the automation code never depends on the
model runtime directly — that keeps unit tests fast and lets the server
run in a separate container/Azure ML endpoint.
"""

from __future__ import annotations

import re

import httpx
from pydantic import BaseModel

from src.common.config import get_settings


class LlmResult(BaseModel):
    text: str
    confidence: float


class LlmInferenceClient:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.llm_inference_url
        self._max_new_tokens = settings.llm_max_new_tokens

    async def generate(self, prompt: str) -> LlmResult:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            response = await client.post(
                "/generate",
                json={"prompt": prompt, "max_new_tokens": self._max_new_tokens},
            )
            response.raise_for_status()
            data = response.json()

        return LlmResult(text=data["text"], confidence=_extract_confidence(data["text"]))


def _extract_confidence(text: str) -> float:
    """Pulls a "confidence 0-1" style number the model was prompted to
    include; falls back to a conservative default if it's missing so a
    malformed generation never silently triggers Tier 3 auto-execution."""
    match = re.search(r"confidence[:\s]*([01](?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    return 0.3

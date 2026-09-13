"""Tier 1: automated first-pass triage.

Classifies severity/false-positive likelihood and drafts an analyst-ready
summary using the fine-tuned LLM, so a human only reviews the model's
output instead of raw log lines.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.ingestion.schema import NormalizedAlert
from src.llm.inference.client import LlmInferenceClient
from src.llm.inference.prompts import build_triage_prompt

logger = get_logger(__name__)


class Tier1Triage:
    def __init__(self, llm_client: LlmInferenceClient | None = None) -> None:
        self._llm_client = llm_client or LlmInferenceClient()

    async def triage(self, alert: NormalizedAlert) -> dict:
        prompt = build_triage_prompt(alert)
        result = await self._llm_client.generate(prompt)
        logger.info(
            "tier1 triage complete",
            extra={"extra_fields": {"alert_id": alert.alert_id}},
        )
        return {
            "alert_id": alert.alert_id,
            "triage_summary": result.text,
            "confidence": result.confidence,
            "recommended_tier": alert.tier,
        }

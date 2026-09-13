"""Tier 3: automated response.

Automated containment (isolating a host via Wazuh active response, blocking
an IP, disabling an account) only fires above CONFIDENCE_THRESHOLD; anything
below that is queued for human approval instead of executed automatically —
containment actions are disruptive and a false positive here has a real
cost, unlike a Tier 1/2 mis-classification which a human simply re-reads.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.ingestion.schema import NormalizedAlert
from src.llm.inference.client import LlmInferenceClient
from src.llm.inference.prompts import build_response_prompt

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.85


class Tier3Response:
    def __init__(self, llm_client: LlmInferenceClient | None = None) -> None:
        self._llm_client = llm_client or LlmInferenceClient()

    async def recommend_response(self, alert: NormalizedAlert, investigation: dict) -> dict:
        prompt = build_response_prompt(alert, investigation)
        result = await self._llm_client.generate(prompt)

        auto_execute = result.confidence >= CONFIDENCE_THRESHOLD
        logger.info(
            "tier3 response evaluated",
            extra={
                "extra_fields": {
                    "alert_id": alert.alert_id,
                    "confidence": result.confidence,
                    "auto_execute": auto_execute,
                }
            },
        )
        return {
            "alert_id": alert.alert_id,
            "recommended_action": result.text,
            "confidence": result.confidence,
            "auto_execute": auto_execute,
            "status": "executed" if auto_execute else "pending_human_approval",
        }

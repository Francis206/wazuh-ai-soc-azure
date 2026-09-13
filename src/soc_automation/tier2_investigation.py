"""Tier 2: correlation and enrichment.

Takes the Tier 1 output for alerts the rule engine flagged as recurring
(ml_pipeline_tier2 group, see wazuh/rules/local_ml_rules.xml) and asks the
LLM to correlate them against recent alert history and produce an
investigation narrative + IOC list.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.ingestion.schema import NormalizedAlert
from src.llm.inference.client import LlmInferenceClient
from src.llm.inference.prompts import build_investigation_prompt

logger = get_logger(__name__)


class Tier2Investigation:
    def __init__(self, llm_client: LlmInferenceClient | None = None) -> None:
        self._llm_client = llm_client or LlmInferenceClient()

    async def investigate(self, alert: NormalizedAlert, related_alerts: list[NormalizedAlert]) -> dict:
        prompt = build_investigation_prompt(alert, related_alerts)
        result = await self._llm_client.generate(prompt)
        logger.info(
            "tier2 investigation complete",
            extra={"extra_fields": {"alert_id": alert.alert_id, "related_count": len(related_alerts)}},
        )
        return {
            "alert_id": alert.alert_id,
            "investigation_narrative": result.text,
            "confidence": result.confidence,
        }

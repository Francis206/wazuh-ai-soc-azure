"""Receives raw Wazuh alert payloads (from the custom integration or a
direct indexer poll), normalizes them, and hands them to the orchestrator.
Kept separate from src/api so the same normalization path can be driven
from a queue consumer (Azure Service Bus/Event Hub) instead of HTTP without
touching the FastAPI layer.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.ingestion.schema import NormalizedAlert, normalize_wazuh_alert
from src.soc_automation.orchestrator import SocOrchestrator

logger = get_logger(__name__)


class AlertListener:
    def __init__(self, orchestrator: SocOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or SocOrchestrator()

    async def handle_raw_alert(self, raw_alert: dict) -> NormalizedAlert:
        alert = normalize_wazuh_alert(raw_alert)
        logger.info(
            "alert received",
            extra={"extra_fields": {"alert_id": alert.alert_id, "tier": alert.tier}},
        )
        await self._orchestrator.process(alert)
        return alert

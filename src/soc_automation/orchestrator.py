"""Routes a normalized alert to the Tier 1/2/3 handler indicated by the
Wazuh rule group it matched, escalating to the next tier's investigation
step only when the current tier's confidence is too low to close it out.
"""

from __future__ import annotations

from src.common.logging import get_logger
from src.ingestion.schema import NormalizedAlert, SocTier
from src.soc_automation.tier1_triage import Tier1Triage
from src.soc_automation.tier2_investigation import Tier2Investigation
from src.soc_automation.tier3_response import Tier3Response

logger = get_logger(__name__)

# Below this, Tier 1's own summary isn't trusted enough to close the alert,
# so it gets escalated to Tier 2 correlation regardless of which Wazuh rule
# group it matched.
ESCALATION_CONFIDENCE_FLOOR = 0.6


class SocOrchestrator:
    def __init__(
        self,
        tier1: Tier1Triage | None = None,
        tier2: Tier2Investigation | None = None,
        tier3: Tier3Response | None = None,
    ) -> None:
        self._tier1 = tier1 or Tier1Triage()
        self._tier2 = tier2 or Tier2Investigation()
        self._tier3 = tier3 or Tier3Response()

    async def process(self, alert: NormalizedAlert) -> dict:
        triage = await self._tier1.triage(alert)

        if alert.tier == SocTier.TIER_1 and triage["confidence"] >= ESCALATION_CONFIDENCE_FLOOR:
            return {"tier": "tier_1", "result": triage}

        investigation = await self._tier2.investigate(alert, related_alerts=[])

        if alert.tier != SocTier.TIER_3:
            return {"tier": "tier_2", "triage": triage, "result": investigation}

        response = await self._tier3.recommend_response(alert, investigation)
        return {"tier": "tier_3", "triage": triage, "investigation": investigation, "result": response}

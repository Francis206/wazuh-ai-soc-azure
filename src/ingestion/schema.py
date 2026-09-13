"""Normalized alert schema shared by ingestion, automation, and the LLM
prompt builder. Wazuh's raw alert JSON is deep and inconsistent across rule
groups, so everything downstream works against this flattened shape instead
of the raw payload.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SocTier(StrEnum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class NormalizedAlert(BaseModel):
    alert_id: str
    source: str = "wazuh"
    rule_id: int
    rule_level: int
    rule_description: str
    agent_name: str | None = None
    agent_ip: str | None = None
    source_ip: str | None = None
    full_log: str | None = None
    tier: SocTier = SocTier.TIER_1
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw: dict = Field(default_factory=dict)


def tier_from_wazuh_groups(groups: list[str]) -> SocTier:
    if "ml_pipeline_tier3" in groups:
        return SocTier.TIER_3
    if "ml_pipeline_tier2" in groups:
        return SocTier.TIER_2
    return SocTier.TIER_1


def normalize_wazuh_alert(raw_alert: dict) -> NormalizedAlert:
    rule = raw_alert.get("rule", {})
    agent = raw_alert.get("agent", {})

    return NormalizedAlert(
        alert_id=str(raw_alert.get("id", raw_alert.get("_id", ""))),
        rule_id=int(rule.get("id", 0)),
        rule_level=int(rule.get("level", 0)),
        rule_description=rule.get("description", ""),
        agent_name=agent.get("name"),
        agent_ip=agent.get("ip"),
        source_ip=raw_alert.get("data", {}).get("srcip"),
        full_log=raw_alert.get("full_log"),
        tier=tier_from_wazuh_groups(rule.get("groups", [])),
        raw=raw_alert,
    )

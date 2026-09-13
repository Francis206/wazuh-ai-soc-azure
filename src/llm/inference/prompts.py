"""Prompt templates for each SOC tier. Kept as plain functions (not a
templating engine) since the structure is simple and stable — a Jinja
dependency would be unjustified overhead here.
"""

from __future__ import annotations

from src.ingestion.schema import NormalizedAlert

SYSTEM_PREAMBLE = (
    "You are a SOC analyst assistant fine-tuned on triage, investigation, "
    "and incident response for Wazuh-generated security alerts. Be precise, "
    "cite the evidence you were given, and never fabricate IOCs."
)


def build_triage_prompt(alert: NormalizedAlert) -> str:
    return (
        f"{SYSTEM_PREAMBLE}\n\n"
        "### Task: Tier 1 Triage\n"
        f"Rule: [{alert.rule_id}] {alert.rule_description} (level {alert.rule_level})\n"
        f"Agent: {alert.agent_name or 'unknown'} ({alert.agent_ip or 'unknown'})\n"
        f"Source IP: {alert.source_ip or 'n/a'}\n"
        f"Raw log: {alert.full_log or 'n/a'}\n\n"
        "Classify this alert (true positive / false positive / needs review), "
        "give a one-paragraph justification, and state your confidence 0-1."
    )


def build_investigation_prompt(alert: NormalizedAlert, related_alerts: list[NormalizedAlert]) -> str:
    related = (
        "\n".join(f"- [{a.rule_id}] {a.rule_description} @ {a.timestamp.isoformat()}" for a in related_alerts)
        or "(none provided)"
    )
    return (
        f"{SYSTEM_PREAMBLE}\n\n"
        "### Task: Tier 2 Investigation\n"
        f"Primary alert: [{alert.rule_id}] {alert.rule_description}\n"
        f"Related alerts in window:\n{related}\n\n"
        "Correlate these events into a single narrative, list any IOCs found "
        "in the given evidence only, and state your confidence 0-1."
    )


def build_response_prompt(alert: NormalizedAlert, investigation: dict) -> str:
    return (
        f"{SYSTEM_PREAMBLE}\n\n"
        "### Task: Tier 3 Response Recommendation\n"
        f"Alert: [{alert.rule_id}] {alert.rule_description}\n"
        f"Investigation narrative: {investigation.get('investigation_narrative', 'n/a')}\n\n"
        "Recommend a single containment action (e.g. isolate host, block IP, "
        "disable account, no action) from the Wazuh active-response catalog "
        "and state your confidence 0-1. Only recommend containment you are "
        "confident is proportionate to the evidence given."
    )

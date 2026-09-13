from src.ingestion.schema import normalize_wazuh_alert
from src.llm.inference.prompts import build_investigation_prompt, build_triage_prompt


def test_build_triage_prompt_includes_rule_and_log(sample_wazuh_alert):
    alert = normalize_wazuh_alert(sample_wazuh_alert)
    prompt = build_triage_prompt(alert)

    assert "100020" in prompt
    assert "Failed password" in prompt
    assert "Tier 1 Triage" in prompt


def test_build_investigation_prompt_handles_no_related_alerts(sample_wazuh_alert):
    alert = normalize_wazuh_alert(sample_wazuh_alert)
    prompt = build_investigation_prompt(alert, [])

    assert "(none provided)" in prompt

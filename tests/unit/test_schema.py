from src.ingestion.schema import SocTier, normalize_wazuh_alert, tier_from_wazuh_groups


def test_normalize_wazuh_alert(sample_wazuh_alert):
    alert = normalize_wazuh_alert(sample_wazuh_alert)

    assert alert.rule_id == 100020
    assert alert.rule_level == 12
    assert alert.agent_name == "web-server-01"
    assert alert.source_ip == "203.0.113.42"
    assert alert.tier == SocTier.TIER_2


def test_tier_from_wazuh_groups_prioritizes_highest_tier():
    assert tier_from_wazuh_groups(["ml_pipeline_tier1", "ml_pipeline_tier3"]) == SocTier.TIER_3
    assert tier_from_wazuh_groups(["ml_pipeline_tier1", "ml_pipeline_tier2"]) == SocTier.TIER_2
    assert tier_from_wazuh_groups(["ml_pipeline_tier1"]) == SocTier.TIER_1
    assert tier_from_wazuh_groups([]) == SocTier.TIER_1

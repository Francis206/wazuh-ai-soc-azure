"""Exercises POST /alerts/wazuh end-to-end through the orchestrator, with the
LLM inference client stubbed so this suite runs without a GPU or a live
model server — real inference behavior is covered by the model evaluation
step in .github/workflows/ml-training.yml instead.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from src.api.main import app
from src.llm.inference.client import LlmResult

client = TestClient(app)


@patch("src.soc_automation.tier2_investigation.LlmInferenceClient")
@patch("src.soc_automation.tier1_triage.LlmInferenceClient")
def test_receive_wazuh_alert_returns_normalized_alert(mock_tier1_cls, mock_tier2_cls, sample_wazuh_alert):
    # sample_wazuh_alert is tier_2, so the orchestrator calls both Tier 1
    # triage and Tier 2 investigation before returning — stub both clients.
    stub_result = LlmResult(text="True positive. Confidence: 0.9", confidence=0.9)
    mock_tier1_cls.return_value.generate = AsyncMock(return_value=stub_result)
    mock_tier2_cls.return_value.generate = AsyncMock(return_value=stub_result)

    response = client.post("/alerts/wazuh", json=sample_wazuh_alert)

    assert response.status_code == 200
    body = response.json()
    assert body["rule_id"] == 100020
    assert body["tier"] == "tier_2"

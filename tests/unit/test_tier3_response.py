import pytest
from src.ingestion.schema import normalize_wazuh_alert
from src.llm.inference.client import LlmResult
from src.soc_automation.tier3_response import CONFIDENCE_THRESHOLD, Tier3Response


class _StubLlmClient:
    def __init__(self, confidence: float) -> None:
        self._confidence = confidence

    async def generate(self, prompt: str) -> LlmResult:
        text = f"Isolate host. Confidence: {self._confidence:.2f}"
        return LlmResult(text=text, confidence=self._confidence)


@pytest.mark.asyncio
async def test_high_confidence_response_auto_executes(sample_wazuh_alert):
    alert = normalize_wazuh_alert(sample_wazuh_alert)
    tier3 = Tier3Response(llm_client=_StubLlmClient(confidence=CONFIDENCE_THRESHOLD + 0.05))

    result = await tier3.recommend_response(alert, investigation={"investigation_narrative": "n/a"})

    assert result["auto_execute"] is True
    assert result["status"] == "executed"


@pytest.mark.asyncio
async def test_low_confidence_response_requires_human_approval(sample_wazuh_alert):
    alert = normalize_wazuh_alert(sample_wazuh_alert)
    tier3 = Tier3Response(llm_client=_StubLlmClient(confidence=CONFIDENCE_THRESHOLD - 0.2))

    result = await tier3.recommend_response(alert, investigation={"investigation_narrative": "n/a"})

    assert result["auto_execute"] is False
    assert result["status"] == "pending_human_approval"

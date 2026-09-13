from src.llm.inference.client import _extract_confidence


def test_extract_confidence_parses_value():
    assert _extract_confidence("Verdict: true positive. Confidence: 0.92") == 0.92


def test_extract_confidence_clamps_to_range():
    assert _extract_confidence("confidence: 1.5") == 1.0


def test_extract_confidence_defaults_when_missing():
    assert _extract_confidence("No confidence stated here.") == 0.3

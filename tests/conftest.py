import pytest


@pytest.fixture
def sample_wazuh_alert() -> dict:
    return {
        "id": "1694612345.123456",
        "rule": {
            "id": 100020,
            "level": 12,
            "description": "Repeated high-severity events from same source: escalate to Tier 2",
            "groups": ["local", "ml_pipeline", "ml_pipeline_tier2"],
        },
        "agent": {"id": "001", "name": "web-server-01", "ip": "10.20.1.10"},
        "data": {"srcip": "203.0.113.42"},
        "full_log": "Failed password for invalid user admin from 203.0.113.42 port 51514 ssh2",
    }

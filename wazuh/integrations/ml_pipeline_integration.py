#!/usr/bin/env python3
"""Wazuh custom integration: forwards eligible alerts to the SOC automation API.

Wazuh invokes custom integrations as `<script> <alert_file> <api_key> [<extra>]`
(see https://documentation.wazuh.com/current/user-manual/manager/integration-with-external-apis.html).
This script reads the alert JSON Wazuh writes to disk and POSTs it to the
ingestion endpoint exposed by `src/api`, rather than duplicating alert
normalization logic here — this file is intentionally a thin, dependency-free
transport shim so it works inside the Wazuh manager container without
installing the project's Python package.
"""
import json
import sys
import urllib.error
import urllib.request

# Alerts below this Wazuh rule level are not worth an LLM triage call.
MIN_RULE_LEVEL = 7


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: ml_pipeline_integration.py <alert_file> <api_key> [soc_api_url]\n")
        return 1

    alert_file, _api_key = sys.argv[1], sys.argv[2]
    soc_api_url = sys.argv[3] if len(sys.argv) > 3 else "http://soc-api:8000/alerts/wazuh"

    with open(alert_file, "r", encoding="utf-8") as fh:
        alert = json.load(fh)

    if alert.get("rule", {}).get("level", 0) < MIN_RULE_LEVEL:
        return 0

    payload = json.dumps(alert).encode("utf-8")
    request = urllib.request.Request(
        soc_api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except urllib.error.URLError as exc:
        sys.stderr.write(f"ml_pipeline_integration: failed to forward alert: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

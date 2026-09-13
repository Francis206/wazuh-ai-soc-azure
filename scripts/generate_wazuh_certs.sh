#!/usr/bin/env bash
# Generates the TLS certs the Wazuh indexer/dashboard need, using Wazuh's
# own cert-generation image so the cert chain matches what those images
# expect (avoids hand-rolling OpenSSL config that drifts from upstream).
set -euo pipefail

cd "$(dirname "$0")/.."

docker run --rm -ti \
  -v "$(pwd)/docker/wazuh/config/certs.yml:/config/certs.yml" \
  -v "$(pwd)/docker/wazuh/config/wazuh_indexer_ssl_certs:/certificates/" \
  wazuh/wazuh-certs-generator:0.0.2

echo "Certs generated under docker/wazuh/config/wazuh_indexer_ssl_certs/"

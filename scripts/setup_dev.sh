#!/usr/bin/env bash
# Local dev bootstrap: venv + deps + pre-commit + .env.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in real values before running the stack."
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install

echo "Setup complete. Run 'make wazuh-up' then 'make api' to start the stack."

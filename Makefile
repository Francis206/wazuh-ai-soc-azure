.PHONY: setup lint format test wazuh-up wazuh-down api train infra-plan infra-apply clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt
	$(VENV)/bin/pre-commit install

lint:
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/black --check src tests
	$(VENV)/bin/mypy src

format:
	$(VENV)/bin/ruff check --fix src tests
	$(VENV)/bin/black src tests

test:
	$(VENV)/bin/pytest tests/unit -v
	$(VENV)/bin/pytest tests/integration -v -m "not azure"

wazuh-up:
	docker compose up -d wazuh.manager wazuh.indexer wazuh.dashboard

wazuh-down:
	docker compose down

api:
	$(VENV)/bin/uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

train:
	$(PYTHON) src/llm/finetune/train.py --config src/llm/finetune/config.yaml

infra-plan:
	cd infra && terraform init -backend-config=environments/dev.backend.hcl && terraform plan -var-file=environments/dev.tfvars

infra-apply:
	cd infra && terraform apply -var-file=environments/dev.tfvars

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

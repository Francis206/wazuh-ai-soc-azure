"""Centralized settings loaded from environment variables (.env in dev,
Key Vault-backed app settings in Azure). Pydantic validates types/required
fields once at import time so misconfiguration fails fast at startup rather
than deep inside a request handler.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Wazuh
    wazuh_api_url: str = Field(default="https://localhost:55000")
    wazuh_api_user: str = Field(default="wazuh-wui")
    wazuh_api_password: str = Field(default="change-me")
    wazuh_indexer_url: str = Field(default="https://localhost:9200")
    wazuh_indexer_user: str = Field(default="admin")
    wazuh_indexer_password: str = Field(default="change-me")

    # Azure
    azure_subscription_id: str | None = None
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_resource_group: str = Field(default="rg-soc-ai-dev")
    azure_ml_workspace: str = Field(default="mlw-soc-ai-dev")
    azure_storage_account: str | None = None
    azure_key_vault_name: str | None = None

    # LLM
    base_model_id: str = Field(default="mistralai/Mistral-7B-Instruct-v0.2")
    fine_tuned_adapter_path: str = Field(default="./ml/models/soc-lora-adapter")
    llm_inference_url: str = Field(default="http://localhost:8001")
    llm_max_new_tokens: int = Field(default=512)

    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()

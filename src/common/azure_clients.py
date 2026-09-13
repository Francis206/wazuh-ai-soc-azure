"""Lazily-constructed Azure SDK clients, shared across the ingestion, LLM,
and automation modules. Centralizing this avoids each module re-deriving
credentials and lets tests substitute fakes via dependency injection.

`DefaultAzureCredential` transparently picks managed identity in Azure and
the service principal / az-cli login locally, so no branching is needed
between environments.
"""

from functools import lru_cache

from src.common.config import get_settings


@lru_cache
def get_credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


@lru_cache
def get_blob_service_client():
    from azure.storage.blob import BlobServiceClient

    settings = get_settings()
    if not settings.azure_storage_account:
        raise RuntimeError("AZURE_STORAGE_ACCOUNT is not configured")
    account_url = f"https://{settings.azure_storage_account}.blob.core.windows.net"
    return BlobServiceClient(account_url=account_url, credential=get_credential())


@lru_cache
def get_secret_client():
    from azure.keyvault.secrets import SecretClient

    settings = get_settings()
    if not settings.azure_key_vault_name:
        raise RuntimeError("AZURE_KEY_VAULT_NAME is not configured")
    vault_url = f"https://{settings.azure_key_vault_name}.vault.azure.net"
    return SecretClient(vault_url=vault_url, credential=get_credential())


@lru_cache
def get_ml_client():
    from azure.ai.ml import MLClient

    settings = get_settings()
    if not settings.azure_subscription_id:
        raise RuntimeError("AZURE_SUBSCRIPTION_ID is not configured")
    return MLClient(
        credential=get_credential(),
        subscription_id=settings.azure_subscription_id,
        resource_group_name=settings.azure_resource_group,
        workspace_name=settings.azure_ml_workspace,
    )

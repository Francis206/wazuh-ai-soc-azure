from functools import lru_cache

from fastapi import APIRouter, HTTPException

from src.common.logging import get_logger
from src.ingestion.alert_listener import AlertListener
from src.ingestion.schema import NormalizedAlert

router = APIRouter(prefix="/alerts", tags=["alerts"])
logger = get_logger(__name__)


@lru_cache
def get_listener() -> AlertListener:
    # Constructed lazily (not at import time) so tests can patch the LLM
    # client class before the first request builds the real dependency chain.
    return AlertListener()


@router.post("/wazuh", response_model=NormalizedAlert)
async def receive_wazuh_alert(raw_alert: dict) -> NormalizedAlert:
    """Entry point for wazuh/integrations/ml_pipeline_integration.py."""
    try:
        return await get_listener().handle_raw_alert(raw_alert)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller as 500
        logger.exception("failed to process alert")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

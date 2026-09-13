from fastapi import FastAPI

from src.api.routers import alerts, health
from src.common.config import get_settings
from src.common.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="AI-Augmented SOC API",
    description="Ingests Wazuh alerts and drives Tier 1-3 automation via a fine-tuned LLM.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(alerts.router)

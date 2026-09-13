"""FastAPI inference server: loads the base model + fine-tuned LoRA adapter
once at startup and exposes a single /generate endpoint. Deployed either as
the `ml-inference` docker-compose service locally, or as an Azure ML online
endpoint in prod (see infra/modules/azure_ml).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from src.common.config import get_settings
from src.common.logging import configure_logging, get_logger

logger = get_logger(__name__)


class GenerateRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 512


class GenerateResponse(BaseModel):
    text: str


@lru_cache
def _load_pipeline():
    """Loads lazily so `import src.llm.inference.server` (e.g. for tests
    that only exercise routing) doesn't pull in torch/transformers."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    settings = get_settings()
    logger.info("loading base model", extra={"extra_fields": {"model": settings.base_model_id}})

    tokenizer = AutoTokenizer.from_pretrained(settings.base_model_id)
    base_model = AutoModelForCausalLM.from_pretrained(
        settings.base_model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    try:
        model = PeftModel.from_pretrained(base_model, settings.fine_tuned_adapter_path)
        logger.info(
            "loaded fine-tuned adapter",
            extra={"extra_fields": {"path": settings.fine_tuned_adapter_path}},
        )
    except Exception:  # noqa: BLE001
        logger.warning("no fine-tuned adapter found, serving base model only")
        model = base_model

    return tokenizer, model


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(get_settings().log_level)
    yield


app = FastAPI(title="SOC LLM Inference Server", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    tokenizer, model = _load_pipeline()

    inputs = tokenizer(request.prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=request.max_new_tokens,
        do_sample=False,
    )
    text = tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    return GenerateResponse(text=text)

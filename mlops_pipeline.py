"""
mlops_pipeline.py — Azure ML pipeline for Mistral 7B SOC fine-tuning.

Stages:
  1. data_prep  — load labeled alerts from Blob, 80/20 split
  2. fine_tune  — LoRA fine-tune Mistral 7B on NC4as_T4_v3 spot GPU
  3. eval_gate  — block promotion if precision < 0.92 or recall < 0.88
  4. register   — push passing model to MLflow model registry

Run:
  python mlops_pipeline.py --env prod --experiment soc-triage-v2
"""

import argparse
import logging
import os
from datetime import datetime

from azure.ai.ml import MLClient, Input, Output, command
from azure.ai.ml.constants import AssetTypes
from azure.ai.ml.dsl import pipeline
from azure.ai.ml.entities import Model, ResourceConfiguration
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_client(subscription_id: str, resource_group: str, workspace: str) -> MLClient:
    return MLClient(DefaultAzureCredential(), subscription_id, resource_group, workspace)


# ── Component: data preparation ───────────────────────────────────────────────
def data_prep_component():
    return command(
        name="soc_data_prep",
        display_name="SOC alert data preparation",
        inputs={"raw_data": Input(type=AssetTypes.URI_FOLDER)},
        outputs={
            "train_data": Output(type=AssetTypes.URI_FOLDER),
            "eval_data":  Output(type=AssetTypes.URI_FOLDER),
        },
        code="./components/data_prep",
        command=(
            "python prep.py "
            "--raw ${{inputs.raw_data}} "
            "--train ${{outputs.train_data}} "
            "--eval ${{outputs.eval_data}}"
        ),
        environment="azureml:soc-training-env:1",
        compute="gpu-spot-cluster",
    )


# ── Component: LoRA fine-tuning ────────────────────────────────────────────────
def finetune_component():
    return command(
        name="soc_finetune",
        display_name="Mistral 7B LoRA fine-tune",
        inputs={
            "train_data":    Input(type=AssetTypes.URI_FOLDER),
            "base_model":    Input(type=AssetTypes.URI_FOLDER),
            "lora_rank":     Input(type="integer", default=16),
            "learning_rate": Input(type="number",  default=2e-4),
            "epochs":        Input(type="integer",  default=3),
        },
        outputs={"model_output": Output(type=AssetTypes.URI_FOLDER)},
        code="./components/finetune",
        command=(
            "python train.py "
            "--train ${{inputs.train_data}} "
            "--base-model ${{inputs.base_model}} "
            "--lora-rank ${{inputs.lora_rank}} "
            "--lr ${{inputs.learning_rate}} "
            "--epochs ${{inputs.epochs}} "
            "--output ${{outputs.model_output}}"
        ),
        environment="azureml:soc-training-env:1",
        compute="gpu-spot-cluster",
        # ResourceConfiguration is required in SDK v2 — plain dict is not accepted
        resources=ResourceConfiguration(instance_count=1),
    )


# ── Component: evaluation gate ────────────────────────────────────────────────
def eval_gate_component():
    return command(
        name="soc_eval",
        display_name="Precision/recall gate",
        inputs={
            "model_output":  Input(type=AssetTypes.URI_FOLDER),
            "eval_data":     Input(type=AssetTypes.URI_FOLDER),
            "min_precision": Input(type="number", default=0.92),
            "min_recall":    Input(type="number", default=0.88),
        },
        outputs={"eval_report": Output(type=AssetTypes.URI_FILE)},
        code="./components/evaluate",
        command=(
            "python evaluate.py "
            "--model ${{inputs.model_output}} "
            "--eval-data ${{inputs.eval_data}} "
            "--min-precision ${{inputs.min_precision}} "
            "--min-recall ${{inputs.min_recall}} "
            "--report ${{outputs.eval_report}}"
        ),
        environment="azureml:soc-training-env:1",
        compute="gpu-spot-cluster",
    )


# ── Pipeline assembly ─────────────────────────────────────────────────────────
@pipeline(
    name="soc_ai_training_pipeline",
    description="Weekly SOC alert model fine-tuning with eval gate and MLflow registry",
)
def soc_pipeline(raw_data_path: str, base_model_path: str):
    prep  = data_prep_component()(raw_data=Input(path=raw_data_path))
    tune  = finetune_component()(
        train_data=prep.outputs.train_data,
        base_model=Input(path=base_model_path),
    )
    evalu = eval_gate_component()(
        model_output=tune.outputs.model_output,
        eval_data=prep.outputs.eval_data,
    )
    return {"eval_report": evalu.outputs.eval_report}


def submit(ml_client: MLClient, raw_data_path: str,
           base_model_path: str, experiment: str) -> str:
    job = soc_pipeline(raw_data_path=raw_data_path, base_model_path=base_model_path)
    job.settings.default_compute   = "gpu-spot-cluster"
    job.settings.default_datastore = "workspaceblobstore"

    submitted = ml_client.jobs.create_or_update(job, experiment_name=experiment)
    logger.info("Pipeline submitted  job=%s  url=%s", submitted.name, submitted.studio_url)
    return submitted.name


def register(ml_client: MLClient, job_name: str,
             model_name: str = "soc-triage-mistral") -> Model:
    """Register model in MLflow registry after eval gate passes."""
    model = Model(
        path=f"azureml://jobs/{job_name}/outputs/model_output",
        name=model_name,
        type=AssetTypes.MLFLOW_MODEL,
        description=f"Mistral 7B SOC triage — {datetime.utcnow().date()}",
        tags={"hipaa_sanitized": "true", "compliance": "hipaa-nist"},
    )
    registered = ml_client.models.create_or_update(model)
    logger.info("Registered  name=%s  version=%s", registered.name, registered.version)
    return registered


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env",        default="prod")
    parser.add_argument("--experiment", default="soc-triage")
    args = parser.parse_args()

    client = get_client(
        subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
        resource_group=f"rg-socai-{args.env}",
        workspace=f"mlw-socai-{args.env}",
    )

    job_name = submit(
        client,
        raw_data_path="azureml://datastores/workspaceblobstore/paths/soc-alerts/labeled/",
        base_model_path="azureml://datastores/workspaceblobstore/paths/models/mistral-7b-base/",
        experiment=args.experiment,
    )
    print(f"Submitted job: {job_name}")

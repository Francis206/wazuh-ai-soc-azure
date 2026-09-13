#!/usr/bin/env python3
"""Submits src/llm/finetune/train.py as an Azure ML command job on the GPU
compute cluster. Kept separate from train.py itself so train.py stays
Azure-agnostic and can run identically on a local GPU box.
"""

from __future__ import annotations

import argparse
import os

import yaml
from azure.ai.ml import Input, MLClient, command
from azure.identity import DefaultAzureCredential


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    ml_client = MLClient(
        credential=DefaultAzureCredential(),
        subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
        resource_group_name=os.environ["AZURE_RESOURCE_GROUP"],
        workspace_name=os.environ["AZURE_ML_WORKSPACE"],
    )

    aml_cfg = cfg["azure_ml"]
    job = command(
        code=".",
        command="python src/llm/finetune/train.py --config src/llm/finetune/config.yaml",
        environment=f"{aml_cfg['environment_name']}@latest",
        compute=aml_cfg["compute_target"],
        experiment_name=aml_cfg["experiment_name"],
        inputs={
            "train_data": Input(type="uri_file", path=cfg["dataset"]["train_path"]),
            "eval_data": Input(type="uri_file", path=cfg["dataset"]["eval_path"]),
        },
    )

    submitted = ml_client.jobs.create_or_update(job)
    print(f"Submitted Azure ML job: {submitted.name} ({submitted.studio_url})")


if __name__ == "__main__":
    main()

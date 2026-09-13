"""QLoRA fine-tuning entry point for the open-source SOC assistant model.

Run locally with a GPU (`make train`) or submitted as an Azure ML command
job by .github/workflows/ml-training.yml — this script has no Azure-specific
code so it runs identically in both places; Azure ML just supplies the
compute and mounts ml/data as an input.
"""

from __future__ import annotations

import argparse

import yaml
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_model_and_tokenizer(cfg: dict):
    import torch

    quant_cfg = cfg["quantization"]
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=quant_cfg["load_in_4bit"],
        bnb_4bit_quant_type=quant_cfg["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=getattr(torch, quant_cfg["bnb_4bit_compute_dtype"]),
    )

    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model_id"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model_id"],
        quantization_config=bnb_config,
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)

    lora_cfg = cfg["lora"]
    peft_config = LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["alpha"],
        lora_dropout=lora_cfg["dropout"],
        target_modules=lora_cfg["target_modules"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    return model, tokenizer


def tokenize_dataset(dataset, tokenizer, prompt_field: str, completion_field: str):
    def _tokenize(example):
        text = example[prompt_field] + "\n" + example[completion_field] + tokenizer.eos_token
        return tokenizer(text, truncation=True, max_length=2048)

    return dataset.map(_tokenize, remove_columns=dataset.column_names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_config(args.config)
    model, tokenizer = build_model_and_tokenizer(cfg)

    ds_cfg = cfg["dataset"]
    raw_datasets = load_dataset(
        "json",
        data_files={"train": ds_cfg["train_path"], "eval": ds_cfg["eval_path"]},
    )
    train_dataset = tokenize_dataset(
        raw_datasets["train"], tokenizer, ds_cfg["prompt_field"], ds_cfg["completion_field"]
    )
    eval_dataset = tokenize_dataset(
        raw_datasets["eval"], tokenizer, ds_cfg["prompt_field"], ds_cfg["completion_field"]
    )

    train_cfg = cfg["training"]
    training_args = TrainingArguments(
        output_dir=cfg["output_dir"],
        num_train_epochs=train_cfg["num_train_epochs"],
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        learning_rate=train_cfg["learning_rate"],
        lr_scheduler_type=train_cfg["lr_scheduler_type"],
        warmup_ratio=train_cfg["warmup_ratio"],
        logging_steps=train_cfg["logging_steps"],
        eval_strategy=train_cfg["eval_strategy"],
        save_strategy=train_cfg["save_strategy"],
        bf16=train_cfg["bf16"],
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
    )
    trainer.train()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])


if __name__ == "__main__":
    main()

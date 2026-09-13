"""Builds the instruction-tuning dataset from labeled SOC incidents.

Expects a source JSONL of historical, analyst-labeled Wazuh alerts (one
object per line: raw alert fields + the analyst's verdict/narrative/action)
and reshapes it into {prompt, completion} pairs matching the prompt
templates in src/llm/inference/prompts.py, so the fine-tuned model learns
to answer exactly the prompts it will be served at inference time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.ingestion.schema import normalize_wazuh_alert
from src.llm.inference.prompts import build_triage_prompt


def build_examples(labeled_incidents_path: Path) -> list[dict]:
    examples = []
    with labeled_incidents_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            alert = normalize_wazuh_alert(record["alert"])
            prompt = build_triage_prompt(alert)
            completion = record["analyst_verdict"]
            examples.append({"prompt": prompt, "completion": completion})
    return examples


def write_jsonl(examples: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for example in examples:
            fh.write(json.dumps(example) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Labeled incidents JSONL")
    parser.add_argument("--train-output", type=Path, default=Path("ml/data/soc_incidents_train.jsonl"))
    parser.add_argument("--eval-output", type=Path, default=Path("ml/data/soc_incidents_eval.jsonl"))
    parser.add_argument("--eval-fraction", type=float, default=0.1)
    args = parser.parse_args()

    examples = build_examples(args.input)
    split_at = max(1, int(len(examples) * (1 - args.eval_fraction)))
    write_jsonl(examples[:split_at], args.train_output)
    write_jsonl(examples[split_at:], args.eval_output)


if __name__ == "__main__":
    main()

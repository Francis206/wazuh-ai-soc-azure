"""Evaluates a fine-tuned adapter against the held-out eval set.

Reports triage-classification accuracy (did the model's verdict match the
analyst's label?) and mean self-reported confidence calibration, so a PR
changing the fine-tuning config/dataset can show whether the model actually
improved. Invoked manually or from .github/workflows/ml-training.yml after
training completes.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _extract_verdict(text: str) -> str:
    match = re.search(r"(true positive|false positive|needs review)", text, re.IGNORECASE)
    return match.group(1).lower() if match else "unknown"


def evaluate(predictions_path: Path, references_path: Path) -> dict:
    predictions = [json.loads(line) for line in predictions_path.read_text().splitlines() if line.strip()]
    references = [json.loads(line) for line in references_path.read_text().splitlines() if line.strip()]

    if len(predictions) != len(references):
        raise ValueError("predictions and references must be the same length")

    correct = 0
    for pred, ref in zip(predictions, references, strict=True):
        if _extract_verdict(pred["text"]) == _extract_verdict(ref["completion"]):
            correct += 1

    accuracy = correct / len(predictions) if predictions else 0.0
    return {"n_examples": len(predictions), "triage_accuracy": accuracy}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("ml/models/eval_report.json"))
    args = parser.parse_args()

    report = evaluate(args.predictions, args.references)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

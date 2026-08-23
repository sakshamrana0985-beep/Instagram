"""Runs pipeline/classify.py against the hand-labeled eval set and reports
accuracy per class (build plan session 4). Requires a real GEMINI_API_KEY.

  python scripts/classify_accuracy.py

The 20-item set in tests/fixtures/classify_eval_set.json is a starter set
covering all six content types - swap in real saved transcripts before
trusting the accuracy number for the >=85% gate.
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")

from google import genai

from config import load_settings
from pipeline.classify import classify

EVAL_SET_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "classify_eval_set.json"


async def main() -> int:
    settings = load_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    examples = json.loads(EVAL_SET_PATH.read_text())

    total = 0
    correct_type = 0
    correct_informational = 0
    per_class_total: dict[str, int] = defaultdict(int)
    per_class_correct: dict[str, int] = defaultdict(int)

    for example in examples:
        label = example["label"]
        result = await classify(client, example["text"])

        total += 1
        per_class_total[label["content_type"]] += 1

        type_ok = result.content_type == label["content_type"]
        info_ok = result.is_informational == label["is_informational"]

        if type_ok:
            correct_type += 1
            per_class_correct[label["content_type"]] += 1
        if info_ok:
            correct_informational += 1

        marker = "OK  " if (type_ok and info_ok) else "MISS"
        print(
            f"[{marker}] expected={label['content_type']:14s} got={result.content_type:14s} "
            f"informational: expected={label['is_informational']!s:5s} got={result.is_informational!s:5s} "
            f"conf={result.confidence:.2f}"
        )

    print("\nPer-class content_type accuracy:")
    for content_type, count in sorted(per_class_total.items()):
        acc = per_class_correct[content_type] / count
        print(f"  {content_type:14s} {per_class_correct[content_type]}/{count} ({acc:.0%})")

    type_accuracy = correct_type / total
    info_accuracy = correct_informational / total
    print(f"\nOverall content_type accuracy: {correct_type}/{total} ({type_accuracy:.0%})")
    print(f"Overall is_informational accuracy: {correct_informational}/{total} ({info_accuracy:.0%})")

    gate = 0.85
    if type_accuracy >= gate:
        print(f"\nPASS - at or above the {gate:.0%} gate.")
        return 0
    print(f"\nBELOW the {gate:.0%} gate - iterate the prompt before proceeding.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

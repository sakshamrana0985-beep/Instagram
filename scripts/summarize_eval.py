"""Runs pipeline/summarize.py against the eval set and prints each summary
next to its source transcript, so a human can eyeball whether anything was
invented or lost (build plan session 5). Requires a real GEMINI_API_KEY.

  python scripts/summarize_eval.py

Only runs items marked is_informational=true in the eval set - the same
gate the real pipeline applies. Do not trust this output unverified: check
every extracted number, name, and code against the source transcript by eye.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from google import genai

from config import load_settings
from pipeline.summarize import summarize

EVAL_SET_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "classify_eval_set.json"


async def main() -> int:
    settings = load_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    examples = json.loads(EVAL_SET_PATH.read_text())

    for example in examples:
        label = example["label"]
        if not label["is_informational"]:
            continue

        result = await summarize(client, label["content_type"], example["text"])

        print("=" * 80)
        print(f"SOURCE ({label['content_type']}):")
        print(f"  {example['text']}")
        print(f"\nSUMMARY (title: {result.title!r}, time_sensitive: {result.is_time_sensitive}):")
        print(json.dumps(result.content, indent=2))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

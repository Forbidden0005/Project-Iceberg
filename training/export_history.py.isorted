"""Export Project Iceberg conversation history to a JSONL fine-tuning dataset.

Reads the long-term memory store and any session logs, formats them as
instruction-following pairs (Alpaca / ShareGPT format), and writes a .jsonl
file ready for unsloth + LoRA training.

Two output formats are supported:

  alpaca  (default):
    {"instruction": "...", "input": "", "output": "..."}
    Works with most LoRA trainers (unsloth, LLaMA-Factory, axolotl).

  sharegpt:
    {"conversations": [{"from": "human", "value": "..."}, {"from": "gpt", "value": "..."}]}
    Better for multi-turn chat fine-tuning.

Usage:
    python training/export_history.py
    python training/export_history.py --format sharegpt --out dataset_chat.jsonl
    python training/export_history.py --log-dir logs/ --out my_dataset.jsonl

The script is intentionally conservative — it only exports turns where both
a user message and an assistant response are present, and skips very short
or uninformative exchanges.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_PATH = "training/dataset.jsonl"
DEFAULT_FORMAT = "alpaca"

# Minimum character length for a turn to be included. Filters out "ok", "yes", etc.
MIN_TURN_CHARS = 30

# Log line format: [2026-05-11 14:32:01] [INFO] USER: message
_LOG_RE = re.compile(
    r"\[[\d\-: ]+\]\s+\[INFO\]\s+(USER|ASSISTANT):\s+(.*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_log_file(path: str) -> list[dict[str, str]]:
    """Parse a structured log file into (role, content) pairs."""
    pairs = []
    current_user: str | None = None

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _LOG_RE.match(line.strip())
                if not m:
                    continue
                role, content = m.group(1).upper(), m.group(2).strip()
                if role == "USER":
                    current_user = content
                elif role == "ASSISTANT" and current_user:
                    pairs.append({"user": current_user, "assistant": content})
                    current_user = None
    except Exception as e:
        print(f"  [warn] Could not parse {path}: {e}", file=sys.stderr)

    return pairs


def _load_memory_store(memory_path: str) -> list[dict[str, str]]:
    """Extract text entries from the JSON memory store as assistant knowledge.

    These become self-contained instruction pairs:
      instruction: "What do you know about: {summary}"
      output:      {text}
    """
    pairs = []
    if not os.path.exists(memory_path):
        return pairs

    try:
        with open(memory_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return pairs

    for item in data:
        text = item.get("text", "").strip()
        if len(text) < MIN_TURN_CHARS:
            continue
        # Make a synthetic QA pair from memory entries
        summary = text[:80].rstrip() + ("..." if len(text) > 80 else "")
        pairs.append(
            {
                "user": f"What do you remember about: {summary}",
                "assistant": text,
            }
        )

    return pairs


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _to_alpaca(pair: dict[str, str]) -> dict:
    return {
        "instruction": pair["user"],
        "input": "",
        "output": pair["assistant"],
    }


def _to_sharegpt(pair: dict[str, str]) -> dict:
    return {
        "conversations": [
            {"from": "human", "value": pair["user"]},
            {"from": "gpt", "value": pair["assistant"]},
        ]
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def export(
    log_dir: str = "logs",
    memory_path: str = "memory_store.json",
    output_path: str = DEFAULT_OUTPUT_PATH,
    fmt: str = DEFAULT_FORMAT,
) -> int:
    """Collect, format, and write training pairs. Returns count written."""

    all_pairs: list[dict[str, str]] = []

    # 1. Parse log files
    if os.path.isdir(log_dir):
        log_files = sorted(f for f in os.listdir(log_dir) if f.endswith(".log"))
        for filename in log_files:
            path = os.path.join(log_dir, filename)
            pairs = _parse_log_file(path)
            print(f"  {filename}: {len(pairs)} turns")
            all_pairs.extend(pairs)
    else:
        print(f"  [info] Log dir '{log_dir}' not found — skipping logs.")

    # 2. Load memory store
    mem_pairs = _load_memory_store(memory_path)
    if mem_pairs:
        print(f"  memory_store.json: {len(mem_pairs)} entries")
        all_pairs.extend(mem_pairs)

    # 3. Filter noise
    all_pairs = [
        p
        for p in all_pairs
        if len(p["user"]) >= MIN_TURN_CHARS and len(p["assistant"]) >= MIN_TURN_CHARS
    ]

    if not all_pairs:
        print("No training pairs found. Run the assistant first to build up history.")
        return 0

    # 4. Format and write
    formatter = _to_alpaca if fmt == "alpaca" else _to_sharegpt
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            f.write(json.dumps(formatter(pair), ensure_ascii=False) + "\n")

    print(f"\nWrote {len(all_pairs)} training pairs → {output_path}")
    return len(all_pairs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Project Iceberg history to a fine-tuning JSONL dataset."
    )
    parser.add_argument(
        "--log-dir", default="logs", help="Directory containing .log files (default: logs/)"
    )
    parser.add_argument(
        "--memory",
        default="memory_store.json",
        help="Path to memory_store.json (default: memory_store.json)",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--format",
        choices=["alpaca", "sharegpt"],
        default=DEFAULT_FORMAT,
        help="Output format: alpaca (default) or sharegpt",
    )
    args = parser.parse_args()

    print(f"Exporting history → {args.out}  [format: {args.format}]")
    count = export(
        log_dir=args.log_dir,
        memory_path=args.memory,
        output_path=args.out,
        fmt=args.format,
    )
    sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()

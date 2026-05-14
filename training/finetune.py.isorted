"""Fine-tune a local LLM on Project Iceberg conversation history using
unsloth + LoRA. Designed for Tyler's GTX 1080 Ti (11 GB VRAM).

Why unsloth:
  - 2x faster training vs plain HuggingFace Trainer
  - 60% less VRAM via 4-bit quantisation + patched attention kernels
  - A 7B model in Q4 fits comfortably in 11 GB with batch_size=2

Typical workflow:
    1. Export history:
       python training/export_history.py --out training/dataset.jsonl

    2. Run fine-tune:
       python training/finetune.py

    3. The adapter lands in training/output_adapter/
       Load it in LM Studio or Ollama with the base model.

VRAM guide for GTX 1080 Ti (11 GB):
    Model          Q4 size   Max batch   Notes
    -------        -------   ---------   -----
    7B  (default)  ~4.5 GB   2–4         Comfortable; plenty of headroom
    13B            ~8.5 GB   1–2         Tight; use gradient_checkpointing=True
    34B            ~20 GB    —           Does not fit; use cloud or quantise more

Adapter output:
  The script saves a LoRA adapter, NOT the full merged model. To use it:

  With LM Studio (GGUF merge):
    python -m unsloth.save_pretrained_merged   # or the merge CLI

  With Ollama (custom Modelfile):
    FROM <base-model>
    ADAPTER ./training/output_adapter

  With HuggingFace directly:
    model, tokenizer = FastLanguageModel.from_pretrained("output_adapter")
"""

from __future__ import annotations

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Config — edit these or pass via CLI flags
# ---------------------------------------------------------------------------

DEFAULT_BASE_MODEL = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
# Other solid choices (all ~4–5 GB Q4, fit on 1080 Ti):
#   "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"  ← great for coding tasks
#   "unsloth/mistral-7b-instruct-v0.3-bnb-4bit"
#   "unsloth/phi-3-mini-4k-instruct-bnb-4bit"       ← very small, fast

DEFAULT_DATASET = "training/dataset.jsonl"
DEFAULT_OUTPUT = "training/output_adapter"

MAX_SEQ_LENGTH = 2048  # token context window during training
LORA_RANK = 16  # LoRA rank: 8–64, higher = more expressive but slower
LORA_ALPHA = 16  # Usually equal to rank
LORA_DROPOUT = 0.05
TRAIN_EPOCHS = 3
BATCH_SIZE = 2  # Per-device batch. 2 is safe for 7B on 1080 Ti.
GRAD_ACCUM = 4  # Effective batch = BATCH_SIZE * GRAD_ACCUM = 8
LEARNING_RATE = 2e-4
WARMUP_RATIO = 0.03
LR_SCHEDULER = "cosine"
WEIGHT_DECAY = 0.01
SEED = 42

# Which layers to apply LoRA to. These are the standard attention + MLP targets.
LORA_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(
    base_model: str = DEFAULT_BASE_MODEL,
    dataset_path: str = DEFAULT_DATASET,
    output_dir: str = DEFAULT_OUTPUT,
    epochs: int = TRAIN_EPOCHS,
    batch_size: int = BATCH_SIZE,
) -> None:

    # --- Validate dataset ---
    if not os.path.exists(dataset_path):
        print(
            f"[finetune] Dataset not found: {dataset_path}\n"
            "Run first: python training/export_history.py"
        )
        sys.exit(1)

    with open(dataset_path, encoding="utf-8") as f:
        sample_count = sum(1 for _ in f)

    if sample_count < 10:
        print(
            f"[finetune] Only {sample_count} training samples found in {dataset_path}.\n"
            "Fine-tuning needs at least ~50 examples to be worthwhile. "
            "Keep using the assistant to build up more history, then re-export."
        )
        sys.exit(1)

    print(f"[finetune] Dataset: {sample_count} samples  →  {dataset_path}")
    print(f"[finetune] Base model: {base_model}")
    print(f"[finetune] Output: {output_dir}")

    # --- Import unsloth (lazy — only needed at training time) ---
    try:
        from datasets import load_dataset  # type: ignore
        from transformers import TrainingArguments  # type: ignore
        from trl import SFTTrainer  # type: ignore
        from unsloth import FastLanguageModel  # type: ignore
    except ImportError as e:
        print(
            f"[finetune] Missing dependency: {e}\n"
            "Install with:\n"
            "  pip install unsloth trl transformers datasets accelerate bitsandbytes\n"
            "For CUDA 11.8 (GTX 1080 Ti):\n"
            "  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
        )
        sys.exit(1)

    # --- Load base model with 4-bit quantisation ---
    print("\n[finetune] Loading base model (4-bit)…")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,  # auto-detect: float16 on 1080 Ti
        load_in_4bit=True,
    )

    # --- Attach LoRA adapters ---
    print("[finetune] Attaching LoRA adapters…")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=LORA_TARGET_MODULES,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",  # unsloth's patched version saves VRAM
        random_state=SEED,
    )

    # --- Load dataset ---
    print("[finetune] Loading dataset…")
    raw_dataset = load_dataset("json", data_files=dataset_path, split="train")

    # Format each sample as a single text string for causal LM training.
    # Alpaca format: ### Instruction:\n{...}\n\n### Response:\n{...}<eos>
    def _format_alpaca(example: dict) -> dict:
        instruction = example.get("instruction", "")
        context = example.get("input", "")
        response = example.get("output", "")

        if context:
            prompt = (
                f"### Instruction:\n{instruction}\n\n"
                f"### Input:\n{context}\n\n"
                f"### Response:\n{response}"
            )
        else:
            prompt = f"### Instruction:\n{instruction}\n\n" f"### Response:\n{response}"
        return {"text": prompt + tokenizer.eos_token}

    def _format_sharegpt(example: dict) -> dict:
        convs = example.get("conversations", [])
        parts = []
        for turn in convs:
            role = "User" if turn.get("from") == "human" else "Assistant"
            parts.append(f"{role}: {turn.get('value', '')}")
        return {"text": "\n".join(parts) + tokenizer.eos_token}

    # Auto-detect format from first sample
    first = raw_dataset[0]
    if "conversations" in first:
        dataset = raw_dataset.map(_format_sharegpt, remove_columns=raw_dataset.column_names)
    else:
        dataset = raw_dataset.map(_format_alpaca, remove_columns=raw_dataset.column_names)

    # --- Training arguments ---
    os.makedirs(output_dir, exist_ok=True)

    training_args = TrainingArguments(
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_ratio=WARMUP_RATIO,
        num_train_epochs=epochs,
        learning_rate=LEARNING_RATE,
        fp16=True,  # 1080 Ti doesn't support bf16
        bf16=False,
        logging_steps=10,
        optim="adamw_8bit",  # 8-bit Adam: less VRAM, same convergence
        weight_decay=WEIGHT_DECAY,
        lr_scheduler_type=LR_SCHEDULER,
        seed=SEED,
        output_dir=output_dir,
        save_strategy="epoch",
        report_to="none",  # disable wandb/tensorboard unless you want it
    )

    # --- Train ---
    print(f"\n[finetune] Starting training ({epochs} epoch(s), batch={batch_size})…")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        dataset_num_proc=2,
        args=training_args,
    )

    trainer.train()

    # --- Save adapter ---
    print(f"\n[finetune] Saving LoRA adapter → {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("\n[finetune] Done!")
    print(f"  Adapter saved to: {os.path.abspath(output_dir)}")
    print("\nTo use with LM Studio:")
    print("  1. Load the base model in LM Studio")
    print(f"  2. Point the LoRA path to: {os.path.abspath(output_dir)}")
    print("\nTo merge into a standalone GGUF:")
    print(
        '  python -c "from unsloth import FastLanguageModel; '
        f"model, tok = FastLanguageModel.from_pretrained('{output_dir}'); "
        f"model.save_pretrained_gguf('{output_dir}_gguf', tok, quantization_method='q4_k_m')\""
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune a local LLM on Project Iceberg history (unsloth + LoRA)."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_BASE_MODEL,
        help=f"Base model to fine-tune (default: {DEFAULT_BASE_MODEL})",
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"Path to JSONL training data (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Directory to save the LoRA adapter (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=TRAIN_EPOCHS,
        help=f"Number of training epochs (default: {TRAIN_EPOCHS})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Per-device batch size (default: {BATCH_SIZE})",
    )
    args = parser.parse_args()

    run(
        base_model=args.model,
        dataset_path=args.dataset,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()

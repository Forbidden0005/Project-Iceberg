"""Persistent long-term memory backed by a JSON file.

Improvements over v1:
  - Deduplication: won't store near-identical entries (cosine > 0.95)
  - Pruning: caps at MAX_ENTRIES, drops oldest entries on overflow
  - Noise filter: skips very short inputs (single words, greetings)
"""

import json
import os

from agent_core.constants import LONG_MEMORY_DEFAULT_TOP_K, LONG_MEMORY_SIMILARITY_THRESHOLD
from utils.embedding import cosine_similarity, text_to_vector

# Entries beyond this count trigger pruning of oldest entries.
MAX_ENTRIES = 200

# Minimum word count for an entry to be worth storing. Single words like
# "hello" or "good" don't add recall value.
MIN_WORDS_TO_STORE = 3

# Similarity threshold for dedup — entries above this are considered duplicates.
DEDUP_SIMILARITY_THRESHOLD = 0.95


class LongMemory:
    def __init__(
        self,
        path: str = "memory_store.json",
        similarity_threshold: float = LONG_MEMORY_SIMILARITY_THRESHOLD,
    ):
        self.path = path
        self.threshold = similarity_threshold
        self.data = self._load()

    def _load(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[long memory save error] {e}")

    def add(self, text: str) -> None:
        """Add text to long-term memory if it's meaningful and not a duplicate."""
        if not text:
            return

        text = text.strip()

        # Skip noise: very short inputs
        word_count = len(text.split())
        if word_count < MIN_WORDS_TO_STORE:
            return

        # Skip raw log lines that leak into memory
        if "[INFO]" in text[:80] and text[:4].isdigit():
            return

        vec = text_to_vector(text)
        if not vec:
            return

        # Dedup check: skip if near-identical entry already exists
        for item in self.data:
            existing_vec = item.get("vec") or {}
            if isinstance(existing_vec, list):
                continue
            if cosine_similarity(vec, existing_vec) >= DEDUP_SIMILARITY_THRESHOLD:
                return

        self.data.append({"text": text, "vec": vec})

        # Prune if over capacity — keep the most recent entries
        if len(self.data) > MAX_ENTRIES:
            self.data = self.data[-MAX_ENTRIES:]

        self._save()

    def search(self, query: str, top_k: int = LONG_MEMORY_DEFAULT_TOP_K) -> list[str]:
        if not query or not self.data:
            return []

        q_vec = text_to_vector(query)
        if not q_vec:
            return []

        scored = []
        for item in self.data:
            vec = item.get("vec") or {}
            # Backwards compat: old list-based vectors get ignored
            if isinstance(vec, list):
                continue
            score = cosine_similarity(q_vec, vec)
            if score >= self.threshold:
                scored.append((score, item["text"]))

        scored.sort(reverse=True)
        return [t for _, t in scored[:top_k]]

    def clear(self) -> None:
        self.data = []
        self._save()

    def deduplicate(self) -> int:
        """Remove near-duplicate entries. Returns count of entries removed.

        Useful for cleaning up existing stores that accumulated duplicates
        before dedup was added.
        """
        if len(self.data) < 2:
            return 0

        keep: list[dict] = []
        removed = 0

        for item in self.data:
            vec = item.get("vec") or {}
            if isinstance(vec, list):
                removed += 1
                continue

            is_dup = False
            for kept in keep:
                kept_vec = kept.get("vec") or {}
                if isinstance(kept_vec, list):
                    continue
                if cosine_similarity(vec, kept_vec) >= DEDUP_SIMILARITY_THRESHOLD:
                    is_dup = True
                    break

            if is_dup:
                removed += 1
            else:
                keep.append(item)

        if removed > 0:
            self.data = keep
            self._save()

        return removed

"""Persistent long-term memory.

Storage backend is selected at runtime:
  - ChromaDB (preferred) -- local on-disk vector store with ANN search.
    Gives true semantic recall: "tell me about my dog" can match an entry
    like "my golden retriever max", not just keyword overlap.
  - JSON flat-file (fallback) -- the original bag-of-words store. Used when
    chromadb is not installed or the collection cannot be opened.

Both backends share the same public interface:
    add(text)           -> store an entry
    search(query, k)    -> return top-k relevant entries
    clear()             -> wipe everything
    deduplicate()       -> remove near-duplicate entries, return count removed
    __len__()           -> number of stored entries
"""

from __future__ import annotations

import json
import os
import uuid

from agent_core.constants import (LONG_MEMORY_DEFAULT_TOP_K,
                                  LONG_MEMORY_SIMILARITY_THRESHOLD)
from utils.embedding import cosine_similarity, get_embedder, text_to_vector

# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------

MAX_ENTRIES = 500
MIN_WORDS_TO_STORE = 3
DEDUP_SIMILARITY_THRESHOLD = 0.95


# ---------------------------------------------------------------------------
# ChromaDB backend
# ---------------------------------------------------------------------------


def _try_import_chroma():
    try:
        import chromadb

        return chromadb
    except ImportError:
        return None


class _ChromaBackend:
    """Persistent vector store using ChromaDB embedded (no-server) mode."""

    def __init__(self, db_path: str) -> None:
        chromadb = _try_import_chroma()
        if chromadb is None:
            raise RuntimeError("chromadb not installed")
        self._embedder = get_embedder()
        client = chromadb.PersistentClient(path=db_path)
        self._col = client.get_or_create_collection(
            name="long_memory",
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self._col.count()

    def add(self, text: str) -> None:
        if not text:
            return
        text = text.strip()
        if len(text.split()) < MIN_WORDS_TO_STORE:
            return
        if _is_log_line(text):
            return

        vec = self._embedder.embed(text)
        if not vec:
            return

        # Dedup check
        if self._col.count() > 0:
            results = self._col.query(
                query_embeddings=[vec] if isinstance(vec, list) else None,
                n_results=1,
                include=["distances"],
            )
            distances = results.get("distances", [[]])[0]
            if distances:
                sim = 1.0 - distances[0]
                if sim >= DEDUP_SIMILARITY_THRESHOLD:
                    return

        doc_id = str(uuid.uuid4())
        embed_arg = [vec] if isinstance(vec, list) else None
        self._col.add(ids=[doc_id], documents=[text], embeddings=embed_arg)

        # Prune oldest if over cap
        total = self._col.count()
        if total > MAX_ENTRIES:
            overflow = total - MAX_ENTRIES
            oldest = self._col.get(limit=overflow, include=[])
            if oldest["ids"]:
                self._col.delete(ids=oldest["ids"])

    def search(self, query: str, top_k: int = LONG_MEMORY_DEFAULT_TOP_K) -> list:
        if not query or self._col.count() == 0:
            return []
        vec = self._embedder.embed(query)
        if not vec:
            return []
        k = min(top_k, self._col.count())
        results = self._col.query(
            query_embeddings=[vec] if isinstance(vec, list) else None,
            n_results=k,
            include=["documents", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return [
            doc
            for doc, dist in zip(docs, distances)
            if (1.0 - dist) >= LONG_MEMORY_SIMILARITY_THRESHOLD
        ]

    def clear(self) -> None:
        all_ids = self._col.get(include=[])["ids"]
        if all_ids:
            self._col.delete(ids=all_ids)

    def deduplicate(self) -> int:
        if self._col.count() < 2:
            return 0
        all_data = self._col.get(include=["documents", "embeddings"])
        ids = all_data["ids"]
        embeddings = all_data.get("embeddings") or []
        if not embeddings:
            return 0
        keep_vecs = []
        to_delete = []
        for doc_id, vec in zip(ids, embeddings):
            is_dup = any(
                cosine_similarity(vec, kept) >= DEDUP_SIMILARITY_THRESHOLD for kept in keep_vecs
            )
            if is_dup:
                to_delete.append(doc_id)
            else:
                keep_vecs.append(vec)
        if to_delete:
            self._col.delete(ids=to_delete)
        return len(to_delete)


# ---------------------------------------------------------------------------
# JSON flat-file backend (fallback)
# ---------------------------------------------------------------------------


class _JsonBackend:
    """Original bag-of-words JSON store. Used when ChromaDB is unavailable."""

    def __init__(self, path: str) -> None:
        self.path = path
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

    def count(self) -> int:
        return len(self.data)

    def add(self, text: str) -> None:
        if not text:
            return
        text = text.strip()
        if len(text.split()) < MIN_WORDS_TO_STORE:
            return
        if _is_log_line(text):
            return
        vec = text_to_vector(text)
        if not vec:
            return
        for item in self.data:
            existing_vec = item.get("vec") or {}
            if isinstance(existing_vec, list):
                continue
            if cosine_similarity(vec, existing_vec) >= DEDUP_SIMILARITY_THRESHOLD:
                return
        self.data.append({"text": text, "vec": vec})
        if len(self.data) > MAX_ENTRIES:
            self.data = self.data[-MAX_ENTRIES:]
        self._save()

    def search(self, query: str, top_k: int = LONG_MEMORY_DEFAULT_TOP_K) -> list:
        if not query or not self.data:
            return []
        q_vec = text_to_vector(query)
        if not q_vec:
            return []
        scored = []
        for item in self.data:
            vec = item.get("vec") or {}
            if isinstance(vec, list):
                continue
            score = cosine_similarity(q_vec, vec)
            if score >= LONG_MEMORY_SIMILARITY_THRESHOLD:
                scored.append((score, item["text"]))
        scored.sort(reverse=True)
        return [t for _, t in scored[:top_k]]

    def clear(self) -> None:
        self.data = []
        self._save()

    def deduplicate(self) -> int:
        if len(self.data) < 2:
            return 0
        keep = []
        removed = 0
        for item in self.data:
            vec = item.get("vec") or {}
            if isinstance(vec, list):
                removed += 1
                continue
            is_dup = any(
                cosine_similarity(vec, k.get("vec") or {}) >= DEDUP_SIMILARITY_THRESHOLD
                for k in keep
                if not isinstance(k.get("vec"), list)
            )
            if is_dup:
                removed += 1
            else:
                keep.append(item)
        if removed > 0:
            self.data = keep
            self._save()
        return removed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_log_line(text: str) -> bool:
    return "[INFO]" in text[:80] and text[:4].isdigit()


def _build_backend(storage_path: str):
    chroma_dir = storage_path + "_chroma"
    try:
        return _ChromaBackend(chroma_dir)
    except Exception:
        pass
    json_path = storage_path if storage_path.endswith(".json") else storage_path + ".json"
    return _JsonBackend(json_path)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


class LongMemory:
    """Persistent long-term memory with automatic backend selection.

    Pass path as a base path (no extension). LongMemory will create either:
      <path>_chroma/   -- ChromaDB directory (preferred)
      <path>.json      -- JSON flat-file (fallback)

    Legacy callers passing "memory_store.json" still work -- the .json
    suffix is stripped and backend auto-detection runs normally.
    """

    def __init__(
        self,
        path: str = "memory_store",
        similarity_threshold: float = LONG_MEMORY_SIMILARITY_THRESHOLD,
    ) -> None:
        base = path.removesuffix(".json") if path.endswith(".json") else path
        self._similarity_threshold = similarity_threshold  # preserved for future backend wiring
        self._backend = _build_backend(base)

    @property
    def backend_name(self) -> str:
        return "chromadb" if isinstance(self._backend, _ChromaBackend) else "json"

    def add(self, text: str) -> None:
        self._backend.add(text)

    def search(self, query: str, top_k: int = LONG_MEMORY_DEFAULT_TOP_K) -> list:
        return self._backend.search(query, top_k)

    def clear(self) -> None:
        self._backend.clear()

    def deduplicate(self) -> int:
        return self._backend.deduplicate()

    def __len__(self) -> int:
        return self._backend.count()

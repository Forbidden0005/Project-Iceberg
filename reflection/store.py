"""
store.py — Persistent lesson store for Project Iceberg's self-improvement system.

Lessons are stored as JSON. Retrieval uses the SmartEmbedder (Ollama nomic-embed-text
when available, bag-of-words cosine similarity otherwise) to find the most relevant
lessons for any given request.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

from reflection.lesson import Lesson
from utils.embedding import SmartEmbedder, cosine_similarity

logger = logging.getLogger(__name__)

# Lessons with effective_confidence below this threshold are not injected
# into the planner, though they remain stored.
_MIN_INJECT_CONFIDENCE = 0.35

# Hard cap on how many lessons we inject per plan.
_MAX_INJECT = 4

# Maximum lessons stored before we prune the least-helpful ones.
_MAX_STORE_SIZE = 200


class LessonStore:
    """Thread-safe, file-backed store for self-improvement lessons.

    Responsibilities:
      - Persist lessons to ``lessons.json`` on every write.
      - Retrieve the top-N most semantically similar lessons for a query.
      - Track use counts and helpfulness so low-quality lessons degrade over time.
    """

    def __init__(self, path: str = "memory/lessons.json") -> None:
        self._path = path
        self._lock = threading.Lock()
        self._embedder = SmartEmbedder()
        self._lessons: list[Lesson] = []
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, lesson: Lesson) -> None:
        """Persist a new lesson, deduplicating near-identical entries."""
        with self._lock:
            if self._is_duplicate(lesson):
                logger.debug("[lessons] skipped duplicate: %s", lesson.text[:60])
                return
            self._lessons.append(lesson)
            self._prune_if_needed()
            self._save()
            logger.info(
                "[lessons] stored new lesson (category=%s, confidence=%.2f): %s",
                lesson.category,
                lesson.confidence,
                lesson.text[:80],
            )

    def search(self, query: str, top_n: int = _MAX_INJECT) -> list[Lesson]:
        """Return the top-N lessons most relevant to *query*.

        Only lessons above _MIN_INJECT_CONFIDENCE are eligible.
        Results are sorted by combined score: similarity x effective_confidence.
        """
        with self._lock:
            candidates = [
                l for l in self._lessons if l.effective_confidence >= _MIN_INJECT_CONFIDENCE
            ]
            if not candidates:
                return []

        # Score outside the lock — embedding can be slow.
        query_vec = self._embedder.embed(query)
        scored: list[tuple[float, Lesson]] = []
        for lesson in candidates:
            lesson_vec = self._embedder.embed(lesson.trigger)
            sim = cosine_similarity(query_vec, lesson_vec)
            score = sim * lesson.effective_confidence
            scored.append((score, lesson))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [lesson for _, lesson in scored[:top_n]]

    def all(self) -> list[Lesson]:
        """Return all stored lessons, newest first."""
        with self._lock:
            return list(reversed(self._lessons))

    def remove(self, lesson_id: str) -> bool:
        """Delete a lesson by ID. Returns True if found and removed."""
        with self._lock:
            before = len(self._lessons)
            self._lessons = [l for l in self._lessons if l.id != lesson_id]
            if len(self._lessons) < before:
                self._save()
                return True
            return False

    def mark_used(self, lesson_ids: list[str], helpful: bool) -> None:
        """Update use_count and helpful_count for a batch of injected lessons."""
        with self._lock:
            changed = False
            for lesson in self._lessons:
                if lesson.id in lesson_ids:
                    lesson.use_count += 1
                    if helpful:
                        lesson.helpful_count += 1
                    changed = True
            if changed:
                self._save()

    def count(self) -> int:
        with self._lock:
            return len(self._lessons)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_duplicate(self, candidate: Lesson) -> bool:
        """True if a very similar lesson already exists (cosine sim > 0.92)."""
        candidate_vec = self._embedder.embed(candidate.text)
        for existing in self._lessons:
            existing_vec = self._embedder.embed(existing.text)
            sim = cosine_similarity(candidate_vec, existing_vec)
            if sim > 0.92:
                return True
        return False

    def _prune_if_needed(self) -> None:
        """If over capacity, drop the lessons with the lowest effective_confidence."""
        if len(self._lessons) <= _MAX_STORE_SIZE:
            return
        self._lessons.sort(key=lambda l: l.effective_confidence, reverse=True)
        dropped = len(self._lessons) - _MAX_STORE_SIZE
        self._lessons = self._lessons[:_MAX_STORE_SIZE]
        logger.info("[lessons] pruned %d low-confidence lessons (store at capacity)", dropped)

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._lessons = [Lesson.from_dict(d) for d in data.get("lessons", [])]
            logger.debug("[lessons] loaded %d lessons from %s", len(self._lessons), self._path)
        except Exception as exc:
            logger.warning("[lessons] failed to load %s: %s", self._path, exc)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"lessons": [l.to_dict() for l in self._lessons]}, f, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.error("[lessons] failed to save: %s", exc)

"""
Simple bag-of-words embedding. No external deps.

This is a big improvement over 26-letter character frequency: it tokenises
properly, lowercases, strips punctuation, and computes cosine similarity
on word-frequency vectors. Good enough for small memory stores; swap in
sentence-transformers later if you want true semantic search.
"""

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Basic English stopwords - trimmed list so short utterances still match
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "to",
    "of",
    "in",
    "on",
    "at",
    "for",
    "with",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "as",
    "by",
    "from",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "me",
    "my",
    "your",
}


def text_to_vector(text: str) -> dict[str, float]:
    if not text:
        return {}
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = sum(counts.values())
    # L1-normalised term frequency
    return {word: count / total for word, count in counts.items()}


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0

    # Dot product over shared keys only
    shared = set(a) & set(b)
    if not shared:
        return 0.0

    dot = sum(a[k] * b[k] for k in shared)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)

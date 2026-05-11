"""Rolling in-memory buffer of the last N interactions."""

from collections import deque
from collections.abc import Iterator
from typing import Any

from agent_core.constants import SHORT_MEMORY_CAPACITY


class ShortMemory:
    def __init__(self, capacity: int = SHORT_MEMORY_CAPACITY):
        self._buf: deque = deque(maxlen=capacity)

    def add(self, item: Any) -> None:
        self._buf.append(item)

    def recent(self, n: int = 5) -> list[Any]:
        if n <= 0:
            return []
        items = list(self._buf)
        return items[-n:]

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._buf)

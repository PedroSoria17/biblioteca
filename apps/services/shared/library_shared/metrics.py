from __future__ import annotations

from collections import Counter
import threading


class Metrics:
    """
    Minimal thread-safe in-process counters (cache hits/misses, Redis
    errors...). Exposed by each service's /health so behavior can be
    observed without adding a metrics stack.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Counter[str] = Counter()

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def get(self, name: str) -> int:
        with self._lock:
            return self._counters[name]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

"""In-memory limiter for failed logins (the app runs as a single process)."""

import threading
import time
from collections import defaultdict, deque


class Pacer:
    """At most one attempt per `seconds` for a key: slows guessing at one account from many addresses without
    locking its owner out (they wait a few seconds at most)."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, key: str) -> float:
        """Seconds until the next attempt is allowed (0: allowed now, and counted)."""
        now = time.monotonic()
        with self._lock:
            last = self._last.get(key)
            if last is not None and now - last < self.seconds:
                return self.seconds - (now - last)
            self._last[key] = now
            return 0.0

    def reset(self, key: str) -> None:
        with self._lock:
            self._last.pop(key, None)


class FailureLimiter:
    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._prune(k, now)) >= self.max_failures for k in keys)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._prune(k, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._hits.pop(k, None)

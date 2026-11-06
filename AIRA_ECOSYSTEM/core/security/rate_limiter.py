"""
AIRA OS — In-Memory Sliding-Window Rate Limiter (Workstream A / OWASP ASVS 5.0).

Protects sensitive endpoints (e.g. /api/v1/auth/login) against automated credential stuffing
and brute-force attacks.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from typing import Dict, Tuple

logger = logging.getLogger("aira.security.rate_limiter")


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: Dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """
        Checks if the request key (e.g. IP address or username) is within allowed rate limit.

        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            q = self._history[key]
            # Prune older timestamps
            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) >= self.max_requests:
                oldest = q[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                return False, retry_after

            q.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        """Resets rate limit history for a specific key (e.g. upon successful login)."""
        with self._lock:
            if key in self._history:
                del self._history[key]


# Global rate limiter instance for auth endpoints: 10 requests per 60 seconds per IP
auth_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

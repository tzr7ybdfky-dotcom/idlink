"""Serialize request starts per hostname and enforce server cooldowns."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit


class DomainBlocked(ValueError):
    """A server refusal stops subsequent requests to this host."""


class DomainRateLimiter:
    """One shared instance serves every plugin in a CLI process."""

    def __init__(
        self,
        interval: float = 2.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if interval < 2.0:
            raise ValueError("minimum interval is 2 seconds")
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._next: dict[str, float] = {}
        self._last: dict[str, float] = {}
        self._intervals: dict[str, float] = {}
        self._blocked: set[str] = set()

    @staticmethod
    def domain(url: str) -> str:
        """Group ports and paths under one hostname."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("only HTTPS URLs are supported")
        return parsed.hostname.lower()

    async def wait(self, url: str) -> None:
        """Reserve a request slot without racing concurrent callers."""
        domain = self.domain(url)
        async with self._locks.setdefault(domain, asyncio.Lock()):
            if domain in self._blocked:
                raise DomainBlocked("domain blocked after access or rate-limit response")
            delay = self._next.get(domain, 0.0) - self.clock()
            if delay > 0:
                await self.sleep(delay)
            self._last[domain] = self.clock()
            self._next[domain] = self._last[domain] + self._intervals.get(domain, self.interval)

    def set_delay(self, url: str, seconds: float) -> None:
        """Apply crawl-delay to start times on this host without an extra post-response wait."""
        domain = self.domain(url)
        delay = max(self.interval, seconds)
        self._intervals[domain] = delay
        if domain in self._last:
            self._next[domain] = max(self._next.get(domain, 0.0), self._last[domain] + delay)

    def block(self, url: str) -> None:
        """Stop further requests for this run after a server refusal."""
        self._blocked.add(self.domain(url))

    def defer(self, url: str, seconds: float) -> None:
        """Honor a robots delay immediately after the policy request."""
        domain = self.domain(url)
        self._next[domain] = max(self._next.get(domain, 0.0), self.clock() + seconds)

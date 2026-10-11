"""Deterministic clocks verify concurrent request spacing."""

import asyncio

import pytest

from idlink.core.ratelimit import DomainRateLimiter


async def test_spacing_and_domain_independence() -> None:
    now = [0.0]
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    limiter = DomainRateLimiter(clock=lambda: now[0], sleep=sleep)
    await asyncio.gather(*(limiter.wait("https://api.github.com/users/x") for _ in range(3)))
    assert sleeps == [2.0, 2.0]
    await limiter.wait("https://habr.com/x")
    assert sleeps == [2.0, 2.0]
    limiter.block("https://api.github.com/robots.txt")
    with pytest.raises(ValueError, match="blocked"):
        await limiter.wait("https://api.github.com/users/y")


def test_interval_cannot_be_lowered() -> None:
    with pytest.raises(ValueError):
        DomainRateLimiter(interval=1)

"""Policy-aware anonymous HTTP transport shared by all plugins."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from idlink import __version__
from idlink.core.native import GoTransport, native_binary
from idlink.core.ratelimit import DomainRateLimiter
from idlink.core.robots import RobotsPolicy
from idlink.plugins.base import PluginError


class PublicHTTP:
    """Respect robots, rate limits and refusals without following redirects."""

    def __init__(
        self,
        repository_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        limiter: DomainRateLimiter | None = None,
        timeout: float = 6.0,
    ) -> None:
        parsed = urlsplit(repository_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or any(char.isspace() for char in repository_url)
        ):
            raise ValueError("repository URL must be a valid HTTPS URL")
        if not 0 < timeout <= 120:
            raise ValueError("timeout must be positive and at most 120 seconds")
        self.timeout = timeout
        self.user_agent = f"idlink/{__version__} (+{repository_url})"
        self.limiter = limiter or DomainRateLimiter()
        if transport is None and (binary := native_binary()):
            transport = GoTransport(binary, timeout=timeout)
        self._resolve_public_hosts = transport is None
        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            limits=httpx.Limits(max_connections=256, max_keepalive_connections=256),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": self.user_agent},
        )
        self._robots: dict[str, RobotsPolicy] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> "PublicHTTP":
        """Enter the managed client lifetime."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Always close network connections."""
        await self.client.aclose()

    async def _request(self, url: str) -> httpx.Response:
        try:
            parsed = urlsplit(url)
            if parsed.username or parsed.password or parsed.port not in {None, 443}:
                raise ValueError("credentials and nonstandard ports are forbidden")
            host = self.limiter.domain(url)
            if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
                raise ValueError("local hosts are forbidden")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                raise ValueError("private addresses are forbidden")
            await self.limiter.wait(url)
            async with asyncio.timeout(self.timeout):
                if self._resolve_public_hosts:
                    addresses = await asyncio.get_running_loop().getaddrinfo(
                        host, 443, type=socket.SOCK_STREAM
                    )
                    if not addresses or any(
                        not ipaddress.ip_address(item[4][0]).is_global for item in addresses
                    ):
                        raise ValueError("host resolves to a private address")
                async with self.client.stream("GET", url, headers={"Cookie": ""}) as streamed:
                    content = bytearray()
                    async for chunk in streamed.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 5_000_000:
                            raise ValueError("response exceeds 5 MB")
                    headers = dict(streamed.headers)
                    for field in ("content-encoding", "content-length", "transfer-encoding"):
                        headers.pop(field, None)
                    response = httpx.Response(
                        streamed.status_code,
                        headers=headers,
                        content=bytes(content),
                        request=streamed.request,
                    )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise PluginError(
                f"таймаут {self.timeout:g} с; существование профиля неизвестно"
            ) from exc
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise PluginError("request failed or domain blocked") from exc
        if response.status_code in {401, 403, 429} or (
            response.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in response.headers
        ):
            self.limiter.block(url)
        return response

    async def get(self, url: str) -> httpx.Response:
        """Check robots before each resource; fail closed on ambiguous policies."""
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        async with self._locks.setdefault(origin, asyncio.Lock()):
            if origin not in self._robots:
                response = await self._request(origin + "/robots.txt")
                if response.status_code in {404, 410}:
                    parser = RobotsPolicy("")
                elif response.status_code == 200:
                    if not response.text.strip() or "<html" in response.text.lower():
                        raise PluginError("unusable robots.txt; request stopped")
                    try:
                        parser = RobotsPolicy(response.text)
                    except ValueError as exc:
                        raise PluginError("unusable robots.txt; request stopped") from exc
                else:
                    raise PluginError("robots.txt unavailable; request stopped")
                self._robots[origin] = parser
            policy = self._robots[origin]
            if not policy.can_fetch(url):
                raise PluginError("robots.txt disallows this resource")
            self.limiter.set_delay(url, policy.delay)
        return await self._request(url)

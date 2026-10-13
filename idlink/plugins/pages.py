"""Follow only canonical HTTPS redirects that preserve the requested public profile route."""

from urllib.parse import unquote, urljoin, urlsplit

import httpx

from idlink.core.http import PublicHTTP


def canonical_redirect(source: str, location: str) -> str | None:
    """Allow www/trailing-slash canonicalisation, never login routes or another service."""
    target = urljoin(source, location)
    old, new = urlsplit(source), urlsplit(target)
    try:
        allowed = (
            new.scheme == "https"
            and not new.username
            and not new.password
            and new.port in {None, 443}
            and bool(new.hostname)
            and (new.hostname or "").lower().removeprefix("www.")
            == (old.hostname or "").lower().removeprefix("www.")
            and unquote(new.path).rstrip("/") == unquote(old.path).rstrip("/")
            and new.query == old.query
            and not new.fragment
        )
    except ValueError:
        return None
    return target if allowed else None


async def public_page(http: PublicHTTP, url: str) -> httpx.Response:
    """At most two canonical hops; every hop rechecks robots and its host limiter."""
    seen = {url}
    response = await http.get(url)
    for _ in range(2):
        if response.status_code not in {301, 302, 303, 307, 308}:
            break
        if (
            "retry-after" in response.headers
            or response.headers.get("x-ratelimit-remaining") == "0"
        ):
            break
        target = canonical_redirect(str(response.request.url), response.headers.get("location", ""))
        if not target or target in seen:
            break
        seen.add(target)
        response = await http.get(target)
    return response

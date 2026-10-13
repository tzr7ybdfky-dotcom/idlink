"""Loopback-only browser UI with one long-lived policy-aware HTTP client."""

import asyncio
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from idlink.core.catalog import SOURCES
from idlink.core.collection import collect, plan_seeds
from idlink.core.graph import Report
from idlink.core.http import PublicHTTP
from idlink.core.report import render_html


class SearchRequest(BaseModel):
    """Validate browser requests before any upstream request is made."""

    model_config = ConfigDict(extra="forbid")
    seed: str = Field(min_length=1, max_length=80)
    mode: Literal["audit", "search"] = "audit"
    purpose: str = Field(default="", max_length=500)
    platforms: str = Field(default="all", max_length=65_536)
    depth: int = Field(default=0, ge=0, le=1)

    def roots(self) -> list[tuple[str, str]]:
        """Classify the input automatically and validate source selection."""
        if not self.platforms:
            raise ValueError("Выберите хотя бы одну площадку.")
        return plan_seeds(self.seed, self.platforms, [])


def trusted_request(host: str, origin: str, token: str, expected: str, port: int) -> bool:
    """Reject cross-origin callers and DNS rebinding to a loopback listener."""
    address = f"127.0.0.1:{port}"
    return (
        host == address
        and origin == f"http://{address}"
        and secrets.compare_digest(token, expected)
    )


async def search_report(http: PublicHTTP, request: SearchRequest) -> Report:
    """Reuse the same transport and rate limiter across browser searches."""
    roots = request.roots()
    result = await collect(
        http,
        roots,
        depth=request.depth,
        allowed_platforms=frozenset(name for name, _ in roots)
        if request.platforms not in {"all", "auto"}
        else None,
    )
    return result.report


def serve(
    repository_url: str,
    port: int = 8765,
    *,
    initial_seed: str = "",
    open_browser: bool = False,
    initial_platforms: str = "all",
) -> None:
    """Serve only on IPv4 loopback; requests are serialized and not logged."""
    token = secrets.token_urlsafe(32)
    with asyncio.Runner() as runner:
        http = PublicHTTP(repository_url)
        runner.run(http.__aenter__())

        class Handler(BaseHTTPRequestHandler):
            """Only the UI and its authenticated same-origin search route are served."""

            def log_message(self, format: str, *args: object) -> None:
                """Do not retain search terms or URL access logs."""

            def reply(self, code: int, body: str, mime: str = "application/json") -> None:
                """Disable caching and third-party embedding of the live UI."""
                content = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; "
                    "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                    "connect-src 'self'; frame-src 'self' about:; "
                    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                )
                self.end_headers()
                self.wfile.write(content)

            def do_GET(self) -> None:
                """Return one bundled page without exposing the filesystem."""
                if self.headers.get("Host") != f"127.0.0.1:{port}":
                    self.reply(403, '{"error":"Недопустимый адрес сервера."}')
                elif self.path == "/":
                    page = files("idlink.assets").joinpath("search.html").read_text()
                    page = (
                        page.replace("__TOKEN__", token)
                        .replace(
                            "__INITIAL_SEED__", json.dumps(initial_seed).replace("<", "\\u003c")
                        )
                        .replace("__INITIAL_PLATFORMS__", json.dumps(initial_platforms))
                        .replace(
                            "__SOURCES__",
                            json.dumps(
                                [s.model_dump(mode="json") for s in SOURCES], ensure_ascii=False
                            ).replace("<", "\\u003c"),
                        )
                    )
                    self.reply(200, page, "text/html")
                else:
                    self.reply(404, '{"error":"Страница не найдена."}')

            def do_POST(self) -> None:
                """Validate origin, bounded input and intent before running a lookup."""
                if not trusted_request(
                    self.headers.get("Host", ""),
                    self.headers.get("Origin", ""),
                    self.headers.get("X-idlink-token", ""),
                    token,
                    port,
                ):
                    self.reply(403, '{"error":"Недопустимый источник запроса."}')
                    return
                if self.path != "/api/search":
                    self.reply(404, '{"error":"Маршрут не найден."}')
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if (
                        not 0 < length <= 131_072
                        or self.headers.get("Content-Type") != "application/json"
                    ):
                        raise ValueError("Недопустимый формат запроса.")
                    request = SearchRequest.model_validate_json(self.rfile.read(length))
                    request.roots()
                except ValueError:
                    self.reply(400, '{"error":"Проверьте ник, домен или почту."}')
                    return
                try:
                    report = runner.run(search_report(http, request))
                    self.reply(
                        200,
                        json.dumps(
                            {"report": report.model_dump(mode="json"), "html": render_html(report)},
                            ensure_ascii=False,
                        ),
                    )
                except Exception:
                    self.reply(500, '{"error":"Поиск прерван. Проверьте терминал и источники."}')

        try:
            with HTTPServer(("127.0.0.1", port), Handler) as server:
                if port == 0:
                    port = server.server_port
                print(f"idlink: http://127.0.0.1:{port} · Ctrl+C для остановки", flush=True)
                if open_browser:
                    webbrowser.open(f"http://127.0.0.1:{port}/")
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            runner.run(http.__aexit__())

"""Optional in-memory bridge to the Go GET transport; policy remains in PublicHTTP."""

import asyncio
import base64
import json
import os
import shutil
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, Field


class NativeFrame(BaseModel):
    """Validate response frames before passing them to a platform adapter."""

    id: int
    status: int = 0
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    error: str = ""


def native_binary() -> str | None:
    """Auto-select a local compiled helper; an explicit Python choice bypasses it."""
    engine = os.environ.get("IDLINK_HTTP_ENGINE", "auto")
    if engine not in {"auto", "go", "python"}:
        raise ValueError("IDLINK_HTTP_ENGINE must be auto, go or python")
    if engine == "python":
        return None
    folder = "Scripts" if sys.platform == "win32" else "bin"
    name = "idlink-http.exe" if sys.platform == "win32" else "idlink-http"
    candidates = [
        os.environ.get("IDLINK_NATIVE_HTTP"),
        str(Path(sys.prefix) / folder / name),
        shutil.which("idlink-http"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    if engine == "go":
        raise ValueError("Go helper is not installed; build native/idlink-http first")
    return None


class GoTransport(httpx.AsyncBaseTransport):
    """Multiplex GETs through one native child without persisting response bodies."""

    def __init__(self, binary: str, arguments: tuple[str, ...] = ()) -> None:
        self.binary, self.arguments = binary, arguments
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[NativeFrame]] = {}
        self._start_lock, self._write_lock = asyncio.Lock(), asyncio.Lock()
        self._counter = 0

    async def _start(self) -> asyncio.subprocess.Process:
        async with self._start_lock:
            if self._process is None:
                self._process = await asyncio.create_subprocess_exec(
                    self.binary,
                    *self.arguments,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=8_000_000,
                )
                self._reader = asyncio.create_task(self._read_frames())
            if self._process.returncode is not None or (self._reader and self._reader.done()):
                raise httpx.TransportError("native transport stopped")
            return self._process

    async def _read_frames(self) -> None:
        try:
            process = self._process
            assert process is not None and process.stdout is not None
            while data := await process.stdout.readline():
                frame = NativeFrame.model_validate_json(data)
                if future := self._pending.get(frame.id):
                    if not future.done():
                        future.set_result(frame)
        except (ValueError, OSError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(httpx.TransportError("native transport stopped"))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """No native request is issued outside the existing robots/rate-limit pipeline."""
        if request.method != "GET":
            raise httpx.TransportError("native transport accepts GET only")
        identifier: int | None = None
        try:
            process = await self._start()
            assert process.stdin is not None
            async with self._write_lock:
                self._counter += 1
                identifier = self._counter
                future: asyncio.Future[NativeFrame] = asyncio.get_running_loop().create_future()
                self._pending[identifier] = future
                payload = {
                    "id": identifier,
                    "url": str(request.url),
                    "user_agent": request.headers.get("user-agent", ""),
                }
                process.stdin.write(json.dumps(payload).encode() + b"\n")
                await process.stdin.drain()
            try:
                frame = await future
                if frame.error or not 100 <= frame.status <= 599:
                    raise httpx.TransportError("native request failed")
                body = base64.b64decode(frame.body, validate=True)
                if len(body) > 5_000_000:
                    raise httpx.TransportError("native response exceeds size limit")
                return httpx.Response(frame.status, headers=frame.headers, content=body)
            finally:
                self._pending.pop(identifier, None)
        except (OSError, ValueError) as exc:
            raise httpx.TransportError("native request failed") from exc
        finally:
            if identifier is not None:
                pending = self._pending.pop(identifier, None)
                if pending and not pending.done():
                    pending.cancel()
                elif pending and not pending.cancelled():
                    pending.exception()

    async def aclose(self) -> None:
        """Stop requests and the child when the shared client is closed."""
        if self._reader:
            self._reader.cancel()
            await asyncio.gather(self._reader, return_exceptions=True)
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
            await self._process.wait()

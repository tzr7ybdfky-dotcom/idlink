"""Native IPC is exercised with local protocol fixtures, never real HTTP requests."""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

from idlink.core.native import GoTransport, native_binary


def helper(tmp_path: Path, code: str) -> str:
    """Create a local executable fixture compatible with the NDJSON protocol."""
    path = tmp_path / "fixture-helper"
    path.write_text(f"#!{sys.executable}\n" + code)
    path.chmod(0o700)
    return str(path)


async def test_native_frames_route_out_of_order_without_files(tmp_path: Path) -> None:
    binary = helper(
        tmp_path,
        """import sys,json,base64
pending=[]
for line in sys.stdin:
 pending.append(json.loads(line))
 if len(pending)==2:
  for item in reversed(pending):
   body=base64.b64encode(item['url'].encode()).decode()
   print(json.dumps({'id':item['id'],'status':200,'body':body}),flush=True)
  pending=[]
""",
    )
    transport = GoTransport(sys.executable, (binary,))
    async with httpx.AsyncClient(transport=transport) as client:
        first, second = await asyncio.gather(
            client.get("https://first.example/"), client.get("https://second.example/")
        )
        assert first.text == "https://first.example/"
        assert second.text == "https://second.example/"
    assert not transport._pending
    assert transport._process is not None and transport._process.returncode is not None


async def test_native_unexpected_exit_does_not_hang(tmp_path: Path) -> None:
    binary = helper(tmp_path, "import sys\nsys.stdin.readline()\n")
    async with httpx.AsyncClient(transport=GoTransport(sys.executable, (binary,))) as client:
        with pytest.raises(httpx.TransportError):
            await asyncio.wait_for(client.get("https://example.org/"), timeout=3)
        with pytest.raises(httpx.TransportError):
            await asyncio.wait_for(client.get("https://example.org/again"), timeout=3)


def test_native_engine_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = helper(tmp_path, "pass\n")
    monkeypatch.setenv("IDLINK_NATIVE_HTTP", binary)
    monkeypatch.setenv("IDLINK_HTTP_ENGINE", "auto")
    assert native_binary() == binary
    monkeypatch.setenv("IDLINK_HTTP_ENGINE", "python")
    assert native_binary() is None
    monkeypatch.setenv("IDLINK_HTTP_ENGINE", "invalid")
    with pytest.raises(ValueError):
        native_binary()


@pytest.mark.parametrize("kind", ["dns", "timeout", "policy", "response"])
async def test_native_error_categories_survive_ipc(tmp_path: Path, kind: str) -> None:
    from idlink.core.native import NativeRequestError

    binary = helper(
        tmp_path,
        "import sys,json\nfor line in sys.stdin:\n"
        " item=json.loads(line)\n"
        f" print(json.dumps(dict(id=item['id'],error='failed',error_kind={kind!r})),flush=True)\n",
    )
    async with httpx.AsyncClient(transport=GoTransport(sys.executable, (binary,))) as client:
        with pytest.raises(NativeRequestError) as exc:
            await client.get("https://example.org/")
    assert exc.value.kind == kind

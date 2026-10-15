"""Enroll public Mastodon servers after live metadata and account-endpoint controls."""

import argparse
import asyncio
import hashlib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from idlink.core.catalog import SOURCES
from idlink.core.http import PublicHTTP
from idlink.plugins.base import PluginError
from idlink.plugins.sherlock import engine_identity


def public_domain(value: str) -> bool:
    """Accept DNS names only; PublicHTTP also checks public DNS resolution at request time."""
    return bool(
        len(value) <= 253
        and re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value)
        and not value.endswith((".local", ".localhost", ".internal", ".onion", ".test"))
    )


async def verify(http: PublicHTTP, domain: str) -> dict[str, str] | None:
    """Do not retain contact details, admin handles, profile text or raw responses."""
    try:
        origin = f"https://{domain}"
        response = await http.get(origin + "/api/v2/instance")
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict) or data.get("domain", "").lower() != domain:
            return None
        version = data.get("version", "")
        if not isinstance(version, str) or not re.match(r"[4-9]\.\d+\.", version):
            return None
        if not isinstance(data.get("configuration"), dict):
            return None
        account = data.get("contact", {}).get("account")
        random_name = "idlink" + secrets.token_hex(10)
        negative = await http.get(origin + "/api/v1/accounts/lookup?acct=" + random_name)
        if negative.status_code != 404:
            return None
        missing = negative.json()
        if not isinstance(missing, dict) or missing.get("error") != "Record not found":
            return None
        positive_status = "not_tested"
        if isinstance(account, dict) and isinstance(account.get("username"), str):
            username = account["username"]
            if not re.fullmatch(r"[A-Za-z0-9_]{1,30}", username):
                return None
            positive = await http.get(origin + "/api/v1/accounts/lookup?acct=" + quote(username))
            if positive.status_code != 200 or not engine_identity(
                positive.text, username, "mastodon-user"
            ):
                return None
            identity = positive.json()
            if str(identity.get("id")) != str(account.get("id")):
                return None
            page = urlsplit(identity.get("url", ""))
            if page.scheme != "https" or page.hostname != domain or page.path != "/@" + username:
                return None
            positive_status = "found"
        return {
            "domain": domain,
            "software": "mastodon-compatible",
            "version": version[:80],
            "checked_at": datetime.now(UTC).isoformat(),
            "positive_control": positive_status,
            "negative_control": "missing",
        }
    except (PluginError, ValueError, TypeError, AttributeError, KeyError):
        return None


async def discover(
    peers: Path, output: Path, target: int, concurrency: int, timeout: float
) -> None:
    """Checkpoint accepted domains as JSONL; resume without rechecking accepted hosts."""
    existing = {urlsplit(s.template).hostname for s in SOURCES if s.template}
    records = (
        [json.loads(line) for line in output.read_text().splitlines()] if output.exists() else []
    )
    accepted = {row["domain"] for row in records}
    candidates = {
        str(host).lower().rstrip(".")
        for host in json.loads(peers.read_bytes())
        if isinstance(host, str)
    }
    candidates = {h for h in candidates if public_domain(h) and h not in existing | accepted}
    # Start with likely social servers; within each group use a stable shuffle.
    ordered = sorted(
        candidates,
        key=lambda h: (
            not any(word in h for word in ("masto", "social", "toot", "fosstodon", "mstdn")),
            hashlib.sha256(h.encode()).hexdigest(),
        ),
    )
    queue: asyncio.Queue[str] = asyncio.Queue()
    for domain in ordered:
        queue.put_nowait(domain)
    completed = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    async with PublicHTTP(
        "https://github.com/tzr7ybdfky-dotcom/idlink", timeout=timeout, respect_robots=False
    ) as http:

        async def worker() -> None:
            nonlocal completed
            while len(accepted) < target:
                try:
                    domain = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                result = await verify(http, domain)
                completed += 1
                if result and len(accepted) < target:
                    accepted.add(domain)
                    with output.open("a") as stream:
                        stream.write(json.dumps(result) + "\n")
                if completed % 100 == 0 or len(accepted) >= target:
                    print(
                        f"Checked {completed}; accepted {len(accepted)}/{target}; "
                        f"queued {queue.qsize()}",
                        flush=True,
                    )

        await asyncio.gather(*(worker() for _ in range(concurrency)))
    print(f"Finished: {len(accepted)} accepted servers", flush=True)


def main() -> None:
    """Require a deliberate opt-in before contacting independently operated servers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("peers", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target", type=int, default=3200)
    parser.add_argument("--concurrency", type=int, choices=range(1, 129), default=64)
    parser.add_argument("--timeout", type=float, default=6)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("network discovery requires --live")
    asyncio.run(discover(args.peers, args.out, args.target, args.concurrency, args.timeout))


if __name__ == "__main__":
    main()

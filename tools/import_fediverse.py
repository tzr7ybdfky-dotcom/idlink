"""Bundle only live-checked Fediverse server metadata from discovery JSONL."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from idlink.core.catalog import SOURCES
from idlink.core.fediverse import FederatedServer

ROOT = Path(__file__).resolve().parents[1]


def import_servers(snapshot: Path) -> list[FederatedServer]:
    """Exclude existing hosts and duplicates; reject unvalidated or extra fields."""
    existing = {
        urlsplit(source.template).hostname
        for source in SOURCES
        if source.template and not source.name.startswith("fediverse-")
    }
    selected: dict[str, FederatedServer] = {}
    for line in snapshot.read_text().splitlines():
        server = FederatedServer.model_validate_json(line)
        if server.domain not in existing:
            selected[server.domain] = server
    return sorted(selected.values(), key=lambda server: server.domain)


def main() -> None:
    """Write reproducible metadata, provenance and control counts, without profile data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    servers = import_servers(args.snapshot)
    destination = ROOT / "idlink/data"
    (destination / "fediverse_servers.json").write_text(
        json.dumps([s.model_dump() for s in servers], indent=2) + "\n"
    )
    manifest = {
        "discovery_source": "https://mastodon.social/api/v1/instance/peers",
        "documentation": "https://docs.joinmastodon.org/methods/accounts/#lookup",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "entries": len(servers),
        "snapshot_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
        "positive_controls": dict(Counter(s.positive_control for s in servers)),
        "negative_controls": dict(Counter(s.negative_control for s in servers)),
        "use": "Independently operated servers; direct local profile URLs; no account identities",
        "verification": "Instance metadata, random absent account, optional public contact account",
        "license": "CC0-1.0 (idlink-generated factual server metadata)",
    }
    (destination / "fediverse-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Imported {len(servers)} live-checked server endpoints")


if __name__ == "__main__":
    main()

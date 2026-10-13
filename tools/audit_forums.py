"""Opt-in validation of anonymous Discourse candidates; retain only URLs and statuses."""

import argparse
import asyncio
import json
import secrets
from pathlib import Path

from idlink.core.http import PublicHTTP
from idlink.plugins.base import PluginError
from idlink.plugins.discourse import DiscoursePlugin

CANDIDATES = {
    "Godot Forum": "forum.godotengine.org",
    "Ubuntu Discourse": "discourse.ubuntu.com",
    "Fedora Discussion": "discussion.fedoraproject.org",
    "KDE Discuss": "discuss.kde.org",
    "GNOME Discourse": "discourse.gnome.org",
    "Flathub Discourse": "discourse.flathub.org",
    "EndeavourOS Forum": "forum.endeavouros.com",
    "Manjaro Forum": "forum.manjaro.org",
    "Blender Community": "community.blender.org",
    "Ardour Community": "community.ardour.org",
    "Kakoune Discuss": "discuss.kakoune.com",
    "Haskell Discourse": "discourse.haskell.org",
    "ClojureVerse": "clojureverse.org",
    "OpenStreetMap Community": "community.openstreetmap.org",
    "NixOS Discourse": "discourse.nixos.org",
    "Zorin Forum": "forum.zorin.com",
}


async def audit() -> list[dict[str, str | bool]]:
    """Derive a positive control from the public about endpoint without retaining its body."""
    async with PublicHTTP("https://github.com/tzr7ybdfky-dotcom/idlink") as http:

        async def check(label: str, host: str) -> dict[str, str | bool]:
            row: dict[str, str | bool] = {"label": label, "host": host, "validated": False}
            try:
                async with asyncio.timeout(36):
                    response = await http.get(f"https://{host}/about.json")
                    if response.status_code != 200:
                        raise ValueError(f"about HTTP {response.status_code}")
                    value = response.json()
                    about = value.get("about", {})
                    people = (
                        value.get("users", [])
                        + about.get("admins", [])
                        + about.get("moderators", [])
                    )
                    name = next(p["username"] for p in people if isinstance(p.get("username"), str))
                    plugin = DiscoursePlugin(http, "forum-test", host)
                    positive = await plugin.fetch(name)
                    negative = await plugin.fetch("idlink_" + secrets.token_hex(12))
                    row.update(
                        validated=positive is not None and negative is None,
                        positive_url=positive.url if positive else "",
                        negative="missing" if negative is None else "found",
                    )
            except (PluginError, ValueError, KeyError, StopIteration, TimeoutError) as exc:
                row["error"] = str(exc) or type(exc).__name__
            print(json.dumps(row, ensure_ascii=False), flush=True)
            return row

        return await asyncio.gather(*(check(label, host) for label, host in CANDIDATES.items()))


def main() -> None:
    """Require explicit consent for public network requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("network checks require --live")
    rows = asyncio.run(audit())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

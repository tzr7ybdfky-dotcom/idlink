"""Emit progress and graph snapshots in memory while the full collection continues."""

import time
from collections.abc import Callable

from idlink.core.collection import collect
from idlink.core.graph import Report, SourceCheck, make_report
from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.core.report import render_html


async def stream_collection(
    http: PublicHTTP,
    roots: list[tuple[str, str]],
    emit: Callable[[dict[str, object]], None],
    *,
    depth: int,
    allowed_platforms: frozenset[str] | None = None,
) -> Report:
    """Send the graph before slow sources finish; the final event remains a complete report."""
    profiles: dict[str, Profile] = {}
    last_emit, shown = 0.0, 0
    emit({"type": "start", "total": len(roots), "html": render_html(make_report([]))})

    def found(profile: Profile) -> None:
        profiles[profile.url] = profile

    def checked(check: SourceCheck, count: int, total: int) -> None:
        nonlocal last_emit, shown
        now = time.monotonic()
        first_profile = bool(profiles) and shown == 0
        if not first_profile and now - last_emit < 0.5:
            return
        event: dict[str, object] = {
            "type": "progress",
            "checked": count,
            "total": total,
            "found": len(profiles),
        }
        if len(profiles) != shown:
            report = make_report(
                list(profiles.values()), ["Поиск ещё продолжается."], sparse=len(profiles) > 24
            )
            event["report"] = report.model_dump(mode="json")
            shown = len(profiles)
        emit(event)
        last_emit = now

    result = await collect(
        http,
        roots,
        depth=depth,
        allowed_platforms=allowed_platforms,
        on_profile=found,
        on_check=checked,
    )
    report = result.report
    emit(
        {
            "type": "done",
            "checked": len(report.checks),
            "total": len(roots),
            "found": len(report.nodes),
            "report": report.model_dump(mode="json"),
            "html": render_html(report),
        }
    )
    return report

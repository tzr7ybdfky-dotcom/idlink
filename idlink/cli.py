"""Audit-first CLI with bounded search and offline edge explanations."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from idlink.core.cache import ProfileCache
from idlink.core.collection import Collection, collect, plan_seeds
from idlink.core.http import PublicHTTP
from idlink.core.report import read_report, write_report
from idlink.plugins.base import PluginError

app = typer.Typer(no_args_is_help=True)
Repo = Annotated[str, typer.Option("--repository-url", envvar="IDLINK_REPOSITORY_URL")]
Platforms = Annotated[str, typer.Option("--platforms")]
Out = Annotated[Path, typer.Option("--out")]
Profiles = Annotated[list[str] | None, typer.Option("--profile")]
Activity = Annotated[bool, typer.Option("--activity")]


async def execute(
    roots: list[tuple[str, str]],
    repository_url: str,
    depth: int,
    activity: bool,
) -> Collection:
    """Share one policy-aware client and limiter across all sources."""
    async with PublicHTTP(repository_url) as http:
        return await collect(
            http, roots, depth=depth, activity=activity, cache=ProfileCache(Path(".cache/idlink"))
        )


def run(
    seed: str,
    repository_url: str,
    platforms: str,
    out: Path,
    extra: list[str] | None,
    depth: int,
    activity: bool,
) -> None:
    """Validate inputs first, emit a report and preserve partial-failure exit status."""
    try:
        roots = plan_seeds(seed, platforms, extra or [])
        result = asyncio.run(execute(roots, repository_url, depth, activity))
        write_report(result.report, out)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except PluginError as exc:
        typer.echo(f"Ошибка сети или политики доступа: {exc}", err=True)
        raise typer.Exit(3) from exc
    except OSError as exc:
        typer.echo(f"Ошибка записи отчёта или кэша: {exc}", err=True)
        raise typer.Exit(2) from exc
    for node in result.report.nodes:
        typer.echo(f"{node.platform}: {node.id}")
    for warning in result.report.warnings:
        typer.echo(warning, err=True)
    for identifier, edge in result.report.edges.items():
        typer.echo(f"{identifier}: {edge.probability:.1%} — {edge.verdict}")
    typer.echo(f"Отчёт: {out}")
    if result.has_errors:
        raise typer.Exit(3)


@app.command()
def audit(
    username: str,
    repository_url: Repo,
    platforms: Platforms = "auto",
    out: Out = Path("report.html"),
    profile: Profiles = None,
    activity: Activity = False,
) -> None:
    """Проверить собственные публичные профили (режим по умолчанию)."""
    run(username, repository_url, platforms, out, profile, 1, activity)


@app.command()
def search(
    username: str,
    repository_url: Repo,
    purpose: Annotated[str, typer.Option("--purpose")],
    depth: Annotated[int, typer.Option("--depth", min=0, max=1)] = 1,
    platforms: Platforms = "auto",
    out: Out = Path("report.html"),
    profile: Profiles = None,
    activity: Activity = False,
) -> None:
    """Найти публичные профили с указанной целью и максимум одним переходом."""
    if not purpose.strip():
        raise typer.BadParameter("--purpose не должен быть пустым.")
    typer.echo(
        "Предупреждение: ложные совпадения могут причинить вред; "
        "вероятностная связь не доказывает личность.",
        err=True,
    )
    run(username, repository_url, platforms, out, profile, depth, activity)


@app.command()
def explain(
    edge_id: str,
    report: Annotated[Path, typer.Option("--report")] = Path("report.html"),
) -> None:
    """Показать разбор связи из ранее сохранённого HTML, без сети."""
    try:
        data = read_report(report)
        edge = data.edges[edge_id]
    except (OSError, ValueError, KeyError) as exc:
        raise typer.BadParameter("Отчёт или ID связи не найден либо повреждён.") from exc
    typer.echo(f"{edge.a} ↔ {edge.b}\n{edge.probability:.1%} — {edge.verdict}")
    for signal in edge.signals:
        typer.echo(f"\n{signal.name} (log_lr={signal.log_lr:g}): {signal.explanation}")
        if signal.counter:
            typer.echo(f"Контрдовод: {signal.counter}")


@app.callback()
def default_mode() -> None:
    """Аудит публичных связей; оценки эвристические и не доказывают личность."""


def main() -> None:
    """Treat a bare seed as audit; explicit explain never needs repository configuration."""
    import sys

    args = sys.argv[1:]
    if args and not args[0].startswith("-") and args[0] not in {"audit", "search", "explain"}:
        args.insert(0, "audit")
    app(args=args)

"""Audit-first CLI with bounded search and offline edge explanations."""

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from idlink.core.cache import ProfileCache
from idlink.core.catalog import SOURCES
from idlink.core.categories import CATEGORIES, selected_platforms
from idlink.core.collection import Collection, collect, plan_seeds
from idlink.core.graph import SourceCheck
from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.core.report import read_report, write_report
from idlink.plugins.base import PluginError

PLATFORM_LABELS = {source.name: source.label for source in SOURCES}
PLATFORM_LABELS["website"] = "Website"


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
    on_profile: Callable[[Profile], None] | None = None,
    allowed_platforms: frozenset[str] | None = None,
    timeout: float = 6.0,
    on_check: Callable[[SourceCheck, int, int], None] | None = None,
) -> Collection:
    """Share one policy-aware client and limiter across all sources."""
    async with PublicHTTP(repository_url, timeout=timeout) as http:
        return await collect(
            http,
            roots,
            depth=depth,
            activity=activity,
            cache=ProfileCache(Path(".cache/idlink")),
            on_profile=on_profile,
            allowed_platforms=allowed_platforms,
            on_check=on_check,
        )


def run(
    seed: str,
    repository_url: str,
    platforms: str,
    out: Path | None,
    extra: list[str] | None,
    depth: int,
    activity: bool,
    restrict_sources: bool = False,
    timeout: float = 6.0,
) -> None:
    """Validate inputs first, emit a report and preserve partial-failure exit status."""
    started, last_print = time.monotonic(), 0.0

    def progress(check: SourceCheck, count: int, total: int) -> None:
        nonlocal last_print
        now = time.monotonic()
        if now - last_print >= 2:
            typer.echo(f"Проверено {count}/{total} · {now - started:.0f} с", err=True)
            last_print = now

    try:
        roots = plan_seeds(seed, platforms, extra or [])
        if out is None:
            typer.echo(f"Проверяем {len(roots)} источников…", err=True)
        result = asyncio.run(
            execute(
                roots,
                repository_url,
                depth,
                activity,
                on_profile=(
                    lambda p: typer.echo(
                        f"{PLATFORM_LABELS.get(p.platform, p.platform)}: {p.url}", err=True
                    )
                )
                if out is None
                else None,
                allowed_platforms=frozenset(p for p, _ in roots) if restrict_sources else None,
                timeout=timeout,
                on_check=progress if out is None else None,
            )
        )
        if out is not None:
            write_report(result.report, out)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except PluginError as exc:
        typer.echo(f"Ошибка сети или политики доступа: {exc}", err=True)
        raise typer.Exit(3) from exc
    except OSError as exc:
        typer.echo(f"Ошибка записи отчёта или кэша: {exc}", err=True)
        raise typer.Exit(2) from exc
    for node in sorted(
        result.report.nodes,
        key=lambda node: (PLATFORM_LABELS.get(node.platform, node.platform).casefold(), node.id),
    ):
        typer.echo(f"{PLATFORM_LABELS.get(node.platform, node.platform)}: {node.id}")
    if out is None:
        errors = sum(c.status == "error" for c in result.report.checks)
        typer.echo(
            f"Найдено: {len(result.report.nodes)}. Проверено: {len(result.report.checks)}. "
            f"Недоступно: {errors}. "
            f"Неподтверждено: {sum(c.status == 'unverified' for c in result.report.checks)}.",
            err=True,
        )
        reasons = {
            "robots": "robots.txt",
            "blocked": "блокировки",
            "timeout": "таймауты",
            "dns": "DNS",
            "network": "сеть",
            "http": "HTTP",
            "response": "ответ сервера",
            "redirect": "редиректы",
            "policy": "политика доступа",
        }
        counts = {
            key: sum(
                c.status == "error" and (c.error_kind or "network") == key
                for c in result.report.checks
            )
            for key in reasons
        }
        if errors:
            typer.echo(
                "Причины: "
                + "; ".join(f"{reasons[key]}: {count}" for key, count in counts.items() if count),
                err=True,
            )
    else:
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
    ctx: typer.Context,
    username: str,
    repository_url: Repo = "https://github.com/tzr7ybdfky-dotcom/idlink",
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            min=1,
            max=120,
            help="Сетевой таймаут в секундах; ожидание лимита не включается.",
        ),
    ] = 6.0,
    purpose: Annotated[str | None, typer.Option("--purpose")] = None,
    depth: Annotated[int, typer.Option("--depth", min=0, max=1)] = 1,
    platforms: Platforms = "all",
    out: Annotated[Path | None, typer.Option("--out")] = None,
    profile: Profiles = None,
    activity: Activity = False,
    forums: Annotated[bool, typer.Option("--forums", help="Только: Форумы.")] = False,
    social: Annotated[bool, typer.Option("--social", help="Только: Социальные сети.")] = False,
    dev: Annotated[bool, typer.Option("--dev", help="Только: Разработка.")] = False,
    gaming: Annotated[bool, typer.Option("--gaming", help="Только: Игры.")] = False,
    music: Annotated[bool, typer.Option("--music", help="Только: Музыка.")] = False,
    video: Annotated[bool, typer.Option("--video", help="Только: Видео и стримы.")] = False,
    photo: Annotated[bool, typer.Option("--photo", help="Только: Фотография.")] = False,
    art: Annotated[bool, typer.Option("--art", help="Только: Искусство и дизайн.")] = False,
    blogs: Annotated[bool, typer.Option("--blogs", help="Только: Блоги.")] = False,
    news: Annotated[bool, typer.Option("--news", help="Только: Новости.")] = False,
    science: Annotated[bool, typer.Option("--science", help="Только: Наука.")] = False,
    education: Annotated[bool, typer.Option("--education", help="Только: Образование.")] = False,
    business: Annotated[bool, typer.Option("--business", help="Только: Работа и бизнес.")] = False,
    shopping: Annotated[bool, typer.Option("--shopping", help="Только: Магазины.")] = False,
    sport: Annotated[bool, typer.Option("--sport", help="Только: Спорт.")] = False,
    travel: Annotated[bool, typer.Option("--travel", help="Только: Путешествия.")] = False,
    wikis: Annotated[bool, typer.Option("--wikis", help="Только: Вики.")] = False,
) -> None:
    """Найти публичные профили на всех подключённых источниках."""
    if purpose is not None and not purpose.strip():
        raise typer.BadParameter("--purpose не должен быть пустым.")
    typer.echo(
        "Предупреждение: ложные совпадения могут причинить вред; "
        "вероятностная связь не доказывает личность.",
        err=True,
    )
    try:
        platforms = selected_platforms(platforms, ctx.params)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    run(
        username,
        repository_url,
        platforms,
        out,
        profile,
        depth,
        activity,
        restrict_sources=any(ctx.params.get(k) for k in CATEGORIES),
        timeout=timeout,
    )


@app.command()
def visual(
    ctx: typer.Context,
    username: str,
    repository_url: Repo = "https://github.com/tzr7ybdfky-dotcom/idlink",
    port: Annotated[int, typer.Option("--port", min=0, max=65535)] = 0,
    timeout: Annotated[float, typer.Option("--timeout", min=1, max=120)] = 6.0,
    platforms: Platforms = "all",
    forums: Annotated[bool, typer.Option("--forums", help="Только: Форумы.")] = False,
    social: Annotated[bool, typer.Option("--social", help="Только: Социальные сети.")] = False,
    dev: Annotated[bool, typer.Option("--dev", help="Только: Разработка.")] = False,
    gaming: Annotated[bool, typer.Option("--gaming", help="Только: Игры.")] = False,
    music: Annotated[bool, typer.Option("--music", help="Только: Музыка.")] = False,
    video: Annotated[bool, typer.Option("--video", help="Только: Видео и стримы.")] = False,
    photo: Annotated[bool, typer.Option("--photo", help="Только: Фотография.")] = False,
    art: Annotated[bool, typer.Option("--art", help="Только: Искусство и дизайн.")] = False,
    blogs: Annotated[bool, typer.Option("--blogs", help="Только: Блоги.")] = False,
    news: Annotated[bool, typer.Option("--news", help="Только: Новости.")] = False,
    science: Annotated[bool, typer.Option("--science", help="Только: Наука.")] = False,
    education: Annotated[bool, typer.Option("--education", help="Только: Образование.")] = False,
    business: Annotated[bool, typer.Option("--business", help="Только: Работа и бизнес.")] = False,
    shopping: Annotated[bool, typer.Option("--shopping", help="Только: Магазины.")] = False,
    sport: Annotated[bool, typer.Option("--sport", help="Только: Спорт.")] = False,
    travel: Annotated[bool, typer.Option("--travel", help="Только: Путешествия.")] = False,
    wikis: Annotated[bool, typer.Option("--wikis", help="Только: Вики.")] = False,
) -> None:
    """Открыть сайт и автоматически построить граф по нику, домену или почте."""
    from idlink.web import serve as serve_web

    try:
        platforms = selected_platforms(platforms, ctx.params)
        plan_seeds(username, platforms, [])
        serve_web(
            repository_url,
            port,
            initial_seed=username,
            open_browser=True,
            initial_platforms=platforms,
            timeout=timeout,
        )
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def serve(
    repository_url: Repo,
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8765,
) -> None:
    """Открыть локальный веб-интерфейс поиска на http://127.0.0.1:8765."""
    from idlink.web import serve as serve_web

    try:
        serve_web(repository_url, port)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc


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


@app.command("help")
def show_help() -> None:
    """Показать команды, флаги категорий и примеры поиска."""
    typer.echo("idlink search НИК — ссылки в терминале\nidlink visual НИК — сайт с графом")
    typer.echo("Вместо ника: домен или почта. Без фильтров проверяются все подходящие источники.")
    typer.echo("\nКатегории (несколько флагов объединяются):")
    for flag, (label, _) in CATEGORIES.items():
        typer.echo(f"  --{flag:12} {label}")
    typer.echo("\nДругие флаги: --platforms, --purpose, --depth, --out, --profile, --activity,")
    typer.echo(
        "--repository-url, --timeout; у visual также --port. Подробности: idlink search --help."
    )
    typer.echo("\nidlink search alice --forums --social\nidlink visual alice --gaming")


@app.callback()
def default_mode() -> None:
    """Аудит публичных связей; оценки эвристические и не доказывают личность."""


def main() -> None:
    """Treat a bare seed as audit; explicit explain never needs repository configuration."""
    import sys

    args = sys.argv[1:]
    if (
        args
        and not args[0].startswith("-")
        and args[0] not in {"audit", "search", "explain", "serve", "visual", "help"}
    ):
        args.insert(0, "audit")
    app(args=args)

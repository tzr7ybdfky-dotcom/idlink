"""Opt-in live catalogue audit with explicit coverage; tests never run this network command."""

import argparse
import asyncio
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from idlink.core.catalog import SOURCES
from idlink.core.collection import Collection, collect, plan_seeds
from idlink.core.graph import SourceCheck
from idlink.core.http import PublicHTTP
from tools.catalog_cases import fetch_references, negative_roots


async def audit(username: str, repository: str, timeout: float) -> dict[str, object]:
    """Reuse one limiter for seed, references and controls; refusals stop the host for this run."""
    started = time.monotonic()
    stage = "seed"
    last = 0.0

    def progress(check: SourceCheck, count: int, total: int) -> None:
        nonlocal last
        now = time.monotonic()
        if now - last >= 2 or count == total:
            print(f"{stage}: {count}/{total}, {now - started:.1f}s", flush=True)
            last = now

    def results(result: Collection) -> list[dict[str, object]]:
        return [check.model_dump(mode="json") for check in result.report.checks]

    async with PublicHTTP(repository, timeout=timeout) as http:
        references = await fetch_references(http)
        seed_roots = plan_seeds(username, "all", [])
        seed = await collect(http, seed_roots, depth=0, on_check=progress)
        stage = "public references"
        claimed = await collect(http, references.roots, depth=0, on_check=progress)
        stage = "random negative controls"
        negative = await collect(http, negative_roots(), depth=0, on_check=progress)
    checked = {check.platform for check in claimed.report.checks}
    return {
        "fetched_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "seed": username,
        "catalogue_size": len(SOURCES),
        "seed_counts": dict(Counter(check.status for check in seed.report.checks)),
        "reference_counts": dict(Counter(check.status for check in claimed.report.checks)),
        "negative_counts": dict(Counter(check.status for check in negative.report.checks)),
        "access_reasons": dict(
            Counter(
                check.error_kind
                for check in seed.report.checks + claimed.report.checks + negative.report.checks
                if check.status == "error"
            )
        ),
        "disabled_upstream": sorted(references.disabled),
        "no_public_reference": [s.name for s in SOURCES if s.automatic and s.name not in checked],
        "disabled_catalogue": [s.name for s in SOURCES if not s.automatic],
        "warnings": list(references.warnings),
        "seed_checks": results(seed),
        "reference_checks": results(claimed),
        "negative_checks": results(negative),
        "limitations": "A missing upstream example may have been deleted. Access failures and "
        "unverified references do not validate a detector. No profile text is stored.",
    }


def main() -> None:
    """Require an explicit network opt-in and an output path for the diagnostic artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Enable public network checks")
    parser.add_argument("--username", required=True)
    parser.add_argument("--repository-url", default="https://github.com/tzr7ybdfky-dotcom/idlink")
    parser.add_argument("--timeout", type=float, default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error("network checks require --live")
    report = asyncio.run(audit(args.username, args.repository_url, args.timeout))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k.endswith("counts")}, indent=2))
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()

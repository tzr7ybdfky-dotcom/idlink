# Catalogue audit

UTC: 2026-10-12T12:19:45.309790+00:00. Catalogue: 2161 sources.

| Coverage | Sources |
|---|---:|
| controls_passed | 567 |
| disabled | 8 |
| inconclusive | 1586 |

See [the per-source CSV](catalog-audit.csv). `controls_passed` means a public reference
account was found and a random format-valid handle was absent in this run.
It is evidence for that detector at that time, not a guarantee for every account.
`inconclusive` includes inaccessible endpoints, missing/stale public references and
ambiguous pages. Blocked requests and timeouts never establish absence.
`unexpected_positive` requires investigation; it is not automatically a real account.
Disabled sources are not queried. Domain and email inputs need separate controls.

References come from official Sherlock/Maigret metadata and reviewed Discourse forums.
Requests respect robots.txt, access refusals and a shared two-second hostname limiter.
Only URL templates and statuses are published; no profile text or avatars are stored.

Reproduce from a development checkout:

```sh
python -m tools.audit_catalog --live --username YOUR_USERNAME --out build/audit.json
python -m tools.render_catalog_audit build/audit.json --out docs
```

This is an opt-in live audit. Automated tests use fixtures and prohibit real networking.

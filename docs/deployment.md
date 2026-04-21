# Deployment and Operations

[简体中文](./deployment.zh-CN.md)

> Navigation: [← Tailor Workflow](./tailor.md) · [Documentation Home](./README.md) · [Next: Documentation Home →](./README.md)

## Local Helpers

QuickApply includes:

- `scripts/dev.sh`
- `scripts/run.sh`
- `scripts/docker-entrypoint.sh`
- `scripts/seed_demo_data.py`

Typical local run:

```bash
uv sync --dev
uv run python scripts/seed_demo_data.py --replace
bash scripts/dev.sh
```

## Docker

Typical Docker run:

```bash
docker compose up -d --build
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

Bind mounts:

- `./data -> /app/data`
- `./config -> /app/config`

This means your database, workspaces, and config edits stay on the host.

## Testing

Use:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q
```

## Operational Caveats

- JobSpy can be rate-limited by public job boards
- LinkedIn and Indeed are the most likely sources of `429`
- your browser being able to open a page does not guarantee scraper success
- Tailor requires a local authenticated Codex CLI

## Troubleshooting

### Crawl returns zero jobs

Check:

- profile keywords
- locations
- crawl history warnings
- whether the site likely rate-limited the run

### Tailor cannot send to session

Check:

- `codex` is installed
- `codex` is authenticated locally
- the workspace has a populated `session_instruction.md`

### Docker behaves differently from local

Check:

- `config/search_profiles.yaml`
- mounted `./data`
- mounted `./config`
- container environment variables

---

> Continue: [← Tailor Workflow](./tailor.md) · [Documentation Home](./README.md) · [Next: Documentation Home →](./README.md)

# QuickApply

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

QuickApply is a local job-search operations dashboard for targeted applications.

- Scraping engine: [JobSpy](https://github.com/Bunsly/JobSpy)
- Implementation: Codex
- UI inspiration: sub2api

The public repository ships with a fully synthetic B2B SaaS demo persona so it is safe to share publicly:
`Taylor Brooks`, a commercial operator spanning growth marketing, customer success, support operations, and revenue programs.

## Why This Repo Exists

QuickApply is built for a simple workflow:

1. bring in one or more LaTeX resumes
2. define search profiles that match your market
3. scrape jobs locally with JobSpy
4. filter and track the roles worth applying to
5. open a Tailor workspace and push structured revision instructions into the same Codex session

## Screens

These screenshots were generated from the seeded demo dataset.

![Dashboard](docs/screenshots/dashboard-en.png)
![Crawler](docs/screenshots/crawler-en.png)
![Jobs](docs/screenshots/jobs-en.png)
![Tracker](docs/screenshots/tracker-en.png)

## Quick Start

### Local

```bash
uv sync --dev
uv run python scripts/seed_demo_data.py --replace
uv run python main.py
```

Open:

- `http://127.0.0.1:5273/dashboard`

### Docker

```bash
docker compose up -d --build
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

Open:

- `http://127.0.0.1:5273/dashboard`

## Documentation

Start here:

- [Documentation Home](docs/README.md)
- [Quick Start Guide](docs/getting-started.md)
- [Configuration Guide](docs/configuration.md)
- [Crawler, Jobs, and Tracker Workflow](docs/workflows.md)
- [Tailor Workflow](docs/tailor.md)
- [Deployment and Operations](docs/deployment.md)

Chinese docs:

- [文档首页](docs/README.zh-CN.md)
- [快速开始](docs/getting-started.zh-CN.md)
- [配置说明](docs/configuration.zh-CN.md)
- [抓取与投递流程](docs/workflows.zh-CN.md)
- [Tailor 精修说明](docs/tailor.zh-CN.md)
- [部署与运维](docs/deployment.zh-CN.md)

## Repository Layout

```text
app/                     Flask app, JobSpy fetch flow, scoring, storage, Tailor service
config/                  Search profiles and runtime config
data/                    SQLite DB and generated workspaces
docs/                    Public documentation and screenshots
examples/                Synthetic resumes, project library, proof library, template resume
scripts/                 Startup helpers and demo seeding
static/                  CSS and i18n assets
templates/               Jinja templates
tests/                   Route, config, scoring, and Tailor tests
.codex/skills/           Public Tailor skills
```

## Tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q
```

# QuickApply

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

> 🚀 **QuickApply** turns local resumes, market-specific search profiles, and JobSpy scraping into one focused application operations desk.

<p align="center">
  <strong>JobSpy-powered</strong> ·
  <strong>Built with Codex</strong> ·
  <strong>UI inspired by sub2api</strong>
</p>

QuickApply is built for people who do not want a generic job board dashboard.
It is for targeted application work:

- bring in one or more LaTeX resumes
- define market-aware search profiles
- scrape locally with JobSpy
- review, exclude, and track jobs in one place
- push structured tailoring instructions into the same Codex workflow

## ✨ Why It Feels Different

- **Resume-driven instead of keyword chaos**: profiles and resumes stay close to the actual roles you want.
- **Local-first instead of SaaS lock-in**: data, workspaces, and generated PDFs live on your machine.
- **Operations-oriented instead of list-oriented**: Dashboard, Crawler, Jobs, Tracker, and Tailor form one loop.
- **Dedicated job-page window instead of tab sprawl**: QuickApply reuses one separate Chrome window for job pages, refreshing that window instead of spraying new tabs everywhere.
- **Safe to share publicly**: this public repo ships with a fully synthetic demo persona, `Taylor Brooks`.

## 🧭 The Workflow

1. Import one or more resumes.
2. Create search profiles that match a real market.
3. Run JobSpy-powered crawls locally.
4. Filter the pool down to roles worth attention.
5. Track applications and tailor a resume for the next serious role.

## 🖼️ Product Tour

The screenshots below mirror the real workflow documented in [docs/workflows.md](./docs/workflows.md).

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.md#1-dashboard">
        <img src="./docs/screenshots/dashboard-en.png" alt="Dashboard" width="100%" />
      </a>
      <br />
      <strong>Dashboard</strong>
      <br />
      <sub>See high matches, recent crawls, tracker activity, and tailoring status.</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.md#2-crawler">
        <img src="./docs/screenshots/crawler-en.png" alt="Crawler" width="100%" />
      </a>
      <br />
      <strong>Crawler</strong>
      <br />
      <sub>Manage profiles, keywords, locations, sources, and crawl history.</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.md#3-jobs">
        <img src="./docs/screenshots/jobs-en.png" alt="Jobs" width="100%" />
      </a>
      <br />
      <strong>Jobs</strong>
      <br />
      <sub>Filter aggressively, reuse one dedicated Chrome window for job pages, exclude noise, and launch Tailor.</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.md#4-tracker">
        <img src="./docs/screenshots/tracker-en.png" alt="Tracker" width="100%" />
      </a>
      <br />
      <strong>Tracker</strong>
      <br />
      <sub>Keep applied jobs, manual entries, stages, and notes in one timeline.</sub>
    </td>
  </tr>
</table>

## ⚡ Quick Start

### Local

```bash
uv sync --dev
uv run python scripts/seed_demo_data.py --replace
uv run python main.py
```

Open `http://127.0.0.1:5273/dashboard`.

### Docker

```bash
docker compose up -d --build
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

Open `http://127.0.0.1:5273/dashboard`.

## 📚 Documentation

Start here:

- [Documentation Home](./docs/README.md)
- [Quick Start Guide](./docs/getting-started.md)
- [Configuration Guide](./docs/configuration.md)
- [Workflow Tour](./docs/workflows.md)
- [Tailor Workflow](./docs/tailor.md)
- [Deployment and Operations](./docs/deployment.md)

Chinese docs:

- [文档首页](./docs/README.zh-CN.md)
- [快速开始](./docs/getting-started.zh-CN.md)
- [配置说明](./docs/configuration.zh-CN.md)
- [抓取与投递流程](./docs/workflows.zh-CN.md)
- [Tailor 精修说明](./docs/tailor.zh-CN.md)
- [部署与运维](./docs/deployment.zh-CN.md)

## 🔒 Public Demo Notes

- The example resumes, projects, and references are synthetic.
- The public repo is intentionally positioned around a B2B SaaS commercial persona.
- The screenshots are generated from seeded demo data, not real user records.

## 🗂️ Repository Layout

```text
app/             Flask app, JobSpy fetch flow, scoring, storage, Tailor service
config/          Search profiles and runtime config
data/            SQLite DB and generated workspaces
docs/            Public docs and screenshots
examples/        Synthetic resumes, project library, reference library, templates
scripts/         Startup helpers and demo seeding
static/          CSS, i18n assets, and public-facing static files
templates/       Jinja templates
tests/           Route, config, scoring, and Tailor tests
.codex/skills/   Public Tailor skills
```

## 🧪 Tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q
```

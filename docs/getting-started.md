# Quick Start Guide

[简体中文](./getting-started.zh-CN.md)

## 1. Install Dependencies

### Local

```bash
uv sync --dev
```

### Docker

```bash
docker compose up -d --build
```

## 2. Seed The Demo Dataset

QuickApply ships with a synthetic demo persona and reproducible demo jobs.

### Local

```bash
uv run python scripts/seed_demo_data.py --replace
```

### Docker

```bash
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

This populates:

- jobs
- crawl history
- excluded companies
- application tracks

## 3. Start The App

### Local

```bash
uv run python main.py
```

or:

```bash
bash scripts/dev.sh
```

### Open In Browser

- `http://127.0.0.1:5273/dashboard`

## 4. Replace The Demo Resumes

The public repo includes only synthetic LaTeX resumes.

To use your own:

1. add your `.tex` files
2. update `config/search_profiles.yaml`
3. set:
   - `resume_profile.source_files`
   - `search_profiles[*].default_resume_file`

## 5. First Real Workflow

1. open `Crawler`
2. add or edit a profile
3. run a crawl
4. open `Jobs`
5. filter and review results
6. mark good roles as applied
7. manage them in `Tracker`
8. open a job workspace in `Tailor`

## 6. Recommended Next Reading

- [Configuration Guide](./configuration.md)
- [Crawler, Jobs, and Tracker Workflow](./workflows.md)
- [Tailor Workflow](./tailor.md)

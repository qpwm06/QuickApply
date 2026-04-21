# Configuration Guide

[简体中文](./configuration.zh-CN.md)

## Main Config File

- `config/search_profiles.yaml`

This file defines:

- the global resume profile
- saved search profiles
- default resume selection
- market-priority hints
- proxy file path

## Resume Files

QuickApply expects LaTeX resumes for Tailor.

Recommended layout:

```text
examples/resumes/
  your_general_resume.tex
  your_targeted_resume.tex
```

Important keys:

- `resume_profile.source_files`
- `search_profiles[*].default_resume_file`

## Search Profiles

Each search profile is a reusable scrape bundle.

Important fields:

- `slug`
- `label`
- `search_terms`
- `search_term_weights`
- `locations`
- `sites`
- `default_resume_file`
- `market_priority`

Supported sites:

- `linkedin`
- `indeed`
- `zip_recruiter`

## Environment Variables

- `QUICKAPPLY_CONFIG_PATH`
- `QUICKAPPLY_DATABASE_URL`
- `QUICKAPPLY_WORKSPACES_DIR`
- `QUICKAPPLY_PROXY_FILE`
- `QUICKAPPLY_CODEX_TIMEOUT_SECONDS`
- `PORT`
- `HOST`

## Proxies

If you use rotating proxies:

1. copy `config/proxies.example.txt`
2. save it as `config/proxies.local.txt`
3. put one proxy per line
4. point `QUICKAPPLY_PROXY_FILE` at that file if needed

## Data Storage

By default QuickApply stores runtime data in:

- `data/jobs.db`
- `data/workspaces/`

Those paths are suitable for both local runs and Docker bind mounts.

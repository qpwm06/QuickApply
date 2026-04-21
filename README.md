# QuickApply

[中文说明 / Chinese README](README.zh-CN.md)

QuickApply is a local job-search dashboard for targeted applications. It is powered by
[JobSpy](https://github.com/Bunsly/JobSpy), built with Codex, and its UI direction was inspired by sub2api.

## What It Does

- Runs resume-driven job searches across LinkedIn, Indeed, and ZipRecruiter through JobSpy.
- Scores and filters roles in a compact web UI with tracking and crawler history.
- Keeps an optional Tailor workspace where you can generate resume revision guidance and send structured instructions into the same Codex session.
- Ships with synthetic example resumes and libraries so the repo is safe to publish.

## Important Notes

- This project uses JobSpy for scraping. Public job boards can rate-limit or block requests, especially LinkedIn and Indeed.
- Tailor is included in the open-source version, but live Codex session actions require your own local `codex` CLI and authentication.
- Docker runs the web app and LaTeX toolchain. It does not bundle Codex credentials.

## Repository Layout

```text
app/                     Flask app, fetcher, scoring, storage, Tailor service
config/                  Search profiles and runtime config
examples/                Synthetic resumes, demo project library, demo references
static/                  CSS and i18n assets
templates/               Jinja templates
tests/                   Route and scoring tests
.codex/skills/           Public Tailor skills for revision advice and session send
scripts/                 Local and Docker startup scripts
data/                    SQLite DB and generated Tailor workspaces
```

## Local Development With uv

```bash
uv sync --dev
uv run python main.py
```

Default app URL:

- `http://127.0.0.1:5273/dashboard`

You can also use the helper script:

```bash
bash scripts/dev.sh
```

## Docker Quick Start

```bash
docker compose up -d --build
```

Then open:

- `http://127.0.0.1:5273/dashboard`

The compose file persists runtime data under `./data` and mounts `./config` so you can edit search profiles without rebuilding the image.

## Configuration

Main environment variables:

- `QUICKAPPLY_CONFIG_PATH`
- `QUICKAPPLY_DATABASE_URL`
- `QUICKAPPLY_WORKSPACES_DIR`
- `QUICKAPPLY_PROXY_FILE`
- `QUICKAPPLY_CODEX_TIMEOUT_SECONDS`
- `PORT`
- `HOST`

Copy `config/proxies.example.txt` to `config/proxies.local.txt` if you want to use rotating proxies with JobSpy.

## Tailor Workflow

The Tailor page keeps a single-session workflow:

1. Save the workspace inputs for a job.
2. Generate revision advice from the public Tailor skill.
3. Review or edit the generated `session_instruction.md`.
4. Send the instruction to the same Codex session to update the final LaTeX resume.
5. Review the compiled PDF output in the UI.

If `codex` is not installed or authenticated, the Tailor UI remains available but session execution will fail until you configure it locally.

## Tests

```bash
uv run pytest
```

## Credits

- Scraping engine: JobSpy
- Implementation: Codex
- UI inspiration: sub2api

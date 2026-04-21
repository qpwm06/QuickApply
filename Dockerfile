FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PORT=5273 \
    HOST=0.0.0.0 \
    QUICKAPPLY_CONFIG_PATH=/app/config/search_profiles.yaml \
    QUICKAPPLY_DATABASE_URL=sqlite:///data/jobs.db \
    QUICKAPPLY_WORKSPACES_DIR=data/workspaces

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    latexdiff \
    latexmk \
    texlive-fonts-recommended \
    texlive-latex-base \
    texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN chmod +x scripts/dev.sh scripts/run.sh scripts/docker-entrypoint.sh

EXPOSE 5273

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-5273}/dashboard" >/dev/null || exit 1'

CMD ["scripts/docker-entrypoint.sh"]

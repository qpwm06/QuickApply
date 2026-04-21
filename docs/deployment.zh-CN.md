# 部署与运维

[English](./deployment.md)

## 本地辅助脚本

QuickApply 自带：

- `scripts/dev.sh`
- `scripts/run.sh`
- `scripts/docker-entrypoint.sh`
- `scripts/seed_demo_data.py`

典型本地启动：

```bash
uv sync --dev
uv run python scripts/seed_demo_data.py --replace
bash scripts/dev.sh
```

## Docker

典型 Docker 启动：

```bash
docker compose up -d --build
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

当前 bind mount：

- `./data -> /app/data`
- `./config -> /app/config`

所以数据库、工作区和配置改动都保留在宿主机。

## 测试

使用：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q
```

## 运维边界

- JobSpy 可能被公开招聘站点限流
- LinkedIn 和 Indeed 最容易出现 `429`
- 你浏览器能打开页面，不代表爬虫一定能拿到结果
- Tailor 依赖本机已经登录的 Codex CLI

## 排错建议

### 抓取结果是 0

优先检查：

- 画像关键词
- 地点
- crawl history 里的 warning
- 是否被目标站点限流

### Tailor 不能发给 session

优先检查：

- 本机是否安装了 `codex`
- 本机是否已经登录 `codex`
- 工作区里是否已经有可用的 `session_instruction.md`

### Docker 和本地表现不一致

优先检查：

- `config/search_profiles.yaml`
- 挂载进去的 `./data`
- 挂载进去的 `./config`
- 容器环境变量

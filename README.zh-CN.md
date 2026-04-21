# QuickApply

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

QuickApply 是一个本地优先的职位运营面板。

- 抓取底座： [JobSpy](https://github.com/Bunsly/JobSpy)
- 实现：Codex
- UI 参考：sub2api

公开仓库里默认放的是一套完全虚构的 B2B SaaS demo persona，因此可以安全分享：
`Taylor Brooks`，一个面向增长营销、客户成功、支持运营和 Revenue Programs 的商业岗位候选人。

## 这个仓库解决什么问题

QuickApply 对应的是一条很明确的使用链路：

1. 放入一份或多份 LaTeX 简历
2. 配置和市场方向匹配的搜索画像
3. 用 JobSpy 在本地抓职位
4. 在网页里做筛选、排除、投递追踪
5. 针对具体岗位进入 Tailor，并把结构化指令送进同一个 Codex session

## 页面截图

这些截图都来自演示数据 seed 后的真实页面。

![Dashboard](docs/screenshots/dashboard-en.png)
![Crawler](docs/screenshots/crawler-en.png)
![Jobs](docs/screenshots/jobs-en.png)
![Tracker](docs/screenshots/tracker-en.png)

## 快速启动

### 本地

```bash
uv sync --dev
uv run python scripts/seed_demo_data.py --replace
uv run python main.py
```

打开：

- `http://127.0.0.1:5273/dashboard`

### Docker

```bash
docker compose up -d --build
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

打开：

- `http://127.0.0.1:5273/dashboard`

## Documentation

建议从这里开始看：

- [文档首页](docs/README.zh-CN.md)
- [快速开始](docs/getting-started.zh-CN.md)
- [配置说明](docs/configuration.zh-CN.md)
- [抓取与投递流程](docs/workflows.zh-CN.md)
- [Tailor 精修说明](docs/tailor.zh-CN.md)
- [部署与运维](docs/deployment.zh-CN.md)

英文文档：

- [Documentation Home](docs/README.md)
- [Quick Start Guide](docs/getting-started.md)
- [Configuration Guide](docs/configuration.md)
- [Crawler, Jobs, and Tracker Workflow](docs/workflows.md)
- [Tailor Workflow](docs/tailor.md)
- [Deployment and Operations](docs/deployment.md)

## 仓库结构

```text
app/                     Flask 主应用、JobSpy 抓取、评分、存储、Tailor 服务
config/                  搜索画像和运行配置
data/                    SQLite 数据库和工作区
docs/                    公开文档和截图
examples/                synthetic resumes、项目库、证明材料库、模板简历
scripts/                 启动脚本和 demo seed 脚本
static/                  样式和 i18n
templates/               Jinja 页面模板
tests/                   路由、配置、评分、Tailor 测试
.codex/skills/           公开 Tailor skills
```

## 测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q
```

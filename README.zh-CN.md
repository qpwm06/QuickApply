# QuickApply

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

> 🚀 **QuickApply** 把本地简历、市场导向的搜索画像和 JobSpy 抓取整合成一个真正可运营的投递台。

<p align="center">
  <strong>JobSpy 驱动抓取</strong> ·
  <strong>由 Codex 完成实现</strong> ·
  <strong>UI 参考 sub2api</strong>
</p>

QuickApply 不是泛职位看板，而是面向“定向投递”的本地工作流：

- 放入一份或多份 LaTeX 简历
- 配置真正对应市场的搜索画像
- 用 JobSpy 在本地抓取职位
- 在网页里筛选、排除、追踪岗位
- 针对具体岗位把结构化精修指令送进同一条 Codex 流程

## ✨ 它和普通求职工具有什么不同

- **以简历为中心，不是关键词乱撞**：画像、关键词和默认简历始终围着目标岗位走。
- **本地优先，不是 SaaS 黑箱**：数据、工作区和生成结果都留在自己机器上。
- **更像运营台，不像职位清单**：Dashboard、Crawler、Jobs、Tracker、Tailor 是一条完整链路。
- **岗位页单独占一个 Chrome 窗口，不再疯狂长 tab**：QuickApply 会复用一个独立 Chrome 窗口来打开和刷新岗位页，从而明显减少 tab 数量。
- **可以放心公开分享**：公开仓库默认使用完全虚构的 demo persona `Taylor Brooks`。

## 🧭 整体使用链路

1. 放入一份或多份简历。
2. 建立和市场匹配的搜索画像。
3. 在本地运行 JobSpy 抓取。
4. 从职位池里筛出真正值得处理的岗位。
5. 继续做投递追踪，并针对重点岗位进入 Tailor。

## 🖼️ 页面导览

下面这组截图对应真正的使用流程，详细说明在 [docs/workflows.zh-CN.md](./docs/workflows.zh-CN.md)。

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.zh-CN.md#1-dashboard">
        <img src="./docs/screenshots/dashboard-en.png" alt="Dashboard" width="100%" />
      </a>
      <br />
      <strong>Dashboard</strong>
      <br />
      <sub>先看高分职位、最近抓取、追踪动态和精修进展。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.zh-CN.md#2-crawler">
        <img src="./docs/screenshots/crawler-en.png" alt="Crawler" width="100%" />
      </a>
      <br />
      <strong>Crawler</strong>
      <br />
      <sub>管理画像、关键词、地点、站点来源和抓取历史。</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.zh-CN.md#3-jobs">
        <img src="./docs/screenshots/jobs-en.png" alt="Jobs" width="100%" />
      </a>
      <br />
      <strong>Jobs</strong>
      <br />
      <sub>高强度筛选职位、复用独立 Chrome 窗口查看岗位页、排除噪音公司并进入 Tailor。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="./docs/workflows.zh-CN.md#4-tracker">
        <img src="./docs/screenshots/tracker-en.png" alt="Tracker" width="100%" />
      </a>
      <br />
      <strong>Tracker</strong>
      <br />
      <sub>把已投递岗位、手工录入记录、阶段和备注放到同一条时间线。</sub>
    </td>
  </tr>
</table>

## ⚡ 快速启动

### 本地

```bash
uv sync --dev
uv run python scripts/seed_demo_data.py --replace
uv run python main.py
```

打开 `http://127.0.0.1:5273/dashboard`。

### Docker

```bash
docker compose up -d --build
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

打开 `http://127.0.0.1:5273/dashboard`。

## 📚 Documentation

建议从这里开始：

- [文档首页](./docs/README.zh-CN.md)
- [快速开始](./docs/getting-started.zh-CN.md)
- [配置说明](./docs/configuration.zh-CN.md)
- [抓取与投递流程](./docs/workflows.zh-CN.md)
- [Tailor 精修说明](./docs/tailor.zh-CN.md)
- [部署与运维](./docs/deployment.zh-CN.md)

英文文档：

- [Documentation Home](./docs/README.md)
- [Quick Start Guide](./docs/getting-started.md)
- [Configuration Guide](./docs/configuration.md)
- [Workflow Tour](./docs/workflows.md)
- [Tailor Workflow](./docs/tailor.md)
- [Deployment and Operations](./docs/deployment.md)

## 🔒 公开演示说明

- 示例简历、项目和 reference 都是虚构内容。
- 公开仓库故意切成 B2B SaaS 商业岗位 persona，而不是个人真实材料。
- README 和 docs 使用的截图来自 demo seed 数据，不是任何真实求职记录。

## 🗂️ 仓库结构

```text
app/             Flask 主应用、JobSpy 抓取、评分、存储、Tailor 服务
config/          搜索画像和运行配置
data/            SQLite 数据库和生成工作区
docs/            公开文档和截图
examples/        synthetic resumes、项目库、reference 库、模板
scripts/         启动脚本和 demo seed 脚本
static/          样式、i18n 资源和公开静态文件
templates/       Jinja 页面模板
tests/           路由、配置、评分、Tailor 测试
.codex/skills/   公开 Tailor skills
```

## 🧪 测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run python -m pytest -q
```

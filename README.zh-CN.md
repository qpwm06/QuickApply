# QuickApply

[English README / 英文说明](README.md)

QuickApply 是一个本地优先的职位监控网站。它由
[JobSpy](https://github.com/Bunsly/JobSpy) 驱动抓取，由 Codex 完成实现，UI 风格参考了 sub2api。

## 功能概览

- 基于简历画像，对 LinkedIn、Indeed、ZipRecruiter 做本地职位抓取。
- 在网页里集中做评分、筛选、追踪和抓取历史查看。
- 保留 Tailor/Codex 精修流：生成修改建议、维护同一 Session、把结构化指令发给 Codex 修改最终简历。
- 仓库自带 synthetic example resumes 和示例资料库，可安全公开分享。

## 重要说明

- 项目抓取底座就是 JobSpy；面对 LinkedIn 和 Indeed 这类站点时，仍然可能遇到 429 或反爬限制。
- 开源版保留 Tailor 功能，但真正执行 Codex Session 仍然需要你本地自己安装并登录 `codex` CLI。
- Docker 负责跑 Web 应用和 LaTeX 编译环境，不会自动带上你的 Codex 认证。

## 目录结构

```text
app/                     Flask 主应用、抓取、评分、存储、Tailor 服务
config/                  搜索画像和运行配置
examples/                示例简历、项目库、参考文献库
static/                  样式和 i18n
templates/               页面模板
tests/                   路由和评分测试
.codex/skills/           公开版 Tailor skills
scripts/                 本地启动与 Docker 启动脚本
data/                    SQLite 数据和 Tailor 工作区
```

## 本地启动

```bash
uv sync --dev
uv run python main.py
```

默认地址：

- `http://127.0.0.1:5273/dashboard`

也可以直接用脚本：

```bash
bash scripts/dev.sh
```

## Docker 快速部署

```bash
docker compose up -d --build
```

启动后打开：

- `http://127.0.0.1:5273/dashboard`

`docker-compose.yml` 默认会把运行数据持久化到 `./data`，并把 `./config` 挂载进容器，方便你直接改搜索画像。

## 环境变量

- `QUICKAPPLY_CONFIG_PATH`
- `QUICKAPPLY_DATABASE_URL`
- `QUICKAPPLY_WORKSPACES_DIR`
- `QUICKAPPLY_PROXY_FILE`
- `QUICKAPPLY_CODEX_TIMEOUT_SECONDS`
- `PORT`
- `HOST`

如果你要给 JobSpy 配代理，可以把 `config/proxies.example.txt` 复制成 `config/proxies.local.txt` 后填入代理。

## Tailor 流程

Tailor 页面默认保留单 Session 工作流：

1. 保存岗位工作区输入。
2. 生成修改建议。
3. 审阅或编辑 `session_instruction.md`。
4. 发给同一个 Codex Session 修改最终 LaTeX 简历。
5. 在页面中查看重新编译后的 PDF。

如果本机没有安装或登录 `codex`，Tailor 页面仍然能打开，但执行 Session 动作时会失败，直到你完成本地配置。

## 测试

```bash
uv run pytest
```

## 致谢

- 抓取底座：JobSpy
- 实现：Codex
- UI 参考：sub2api

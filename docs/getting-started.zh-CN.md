# 快速开始

[English](./getting-started.md)

> 导航：[← 文档首页](./README.zh-CN.md) · [下一篇：配置说明 →](./configuration.zh-CN.md)

## 1. 安装依赖

### 本地

```bash
uv sync --dev
```

### Docker

```bash
docker compose up -d --build
```

## 2. 注入演示数据

QuickApply 自带一套完全虚构、可重复生成的 demo 数据。

### 本地

```bash
uv run python scripts/seed_demo_data.py --replace
```

### Docker

```bash
docker compose run --rm quickapply uv run python scripts/seed_demo_data.py --replace
```

这个脚本会写入：

- 职位数据
- 抓取历史
- 排除公司
- 投递追踪

## 3. 启动应用

### 本地

```bash
uv run python main.py
```

或者：

```bash
bash scripts/dev.sh
```

### 打开浏览器

- `http://127.0.0.1:5273/dashboard`

## 4. 替换示例简历

公开仓库里的 LaTeX 简历都是 synthetic 数据。

要换成你自己的：

1. 把 `.tex` 简历放进仓库
2. 修改 `config/search_profiles.yaml`
3. 重点更新：
   - `resume_profile.source_files`
   - `search_profiles[*].default_resume_file`

## 5. 第一次真实使用建议

1. 打开 `Crawler`
2. 添加或修改画像
3. 运行抓取
4. 打开 `Jobs`
5. 做筛选和查看
6. 把值得投的岗位标记为 applied
7. 在 `Tracker` 管理状态
8. 从岗位进入 `Tailor`

## 6. 接下来建议看

- [配置说明](./configuration.zh-CN.md)
- [抓取与投递流程](./workflows.zh-CN.md)
- [Tailor 精修说明](./tailor.zh-CN.md)

---

> 继续阅读：[← 文档首页](./README.zh-CN.md) · [下一篇：配置说明 →](./configuration.zh-CN.md)

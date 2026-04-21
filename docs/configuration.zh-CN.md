# 配置说明

[English](./configuration.md)

> 导航：[← 快速开始](./getting-started.zh-CN.md) · [文档首页](./README.zh-CN.md) · [下一篇：抓取与投递流程 →](./workflows.zh-CN.md)

## 主配置文件

- `config/search_profiles.yaml`

这个文件定义了：

- 全局简历画像
- 保存好的搜索画像
- 默认简历选择
- 市场优先级权重
- 代理文件路径

## 简历文件

QuickApply 的 Tailor 默认使用 LaTeX 简历。

推荐结构：

```text
examples/resumes/
  your_general_resume.tex
  your_targeted_resume.tex
```

关键字段：

- `resume_profile.source_files`
- `search_profiles[*].default_resume_file`

## 搜索画像

每个搜索画像，本质上是一组可复用的抓取配置。

重点字段：

- `slug`
- `label`
- `search_terms`
- `search_term_weights`
- `locations`
- `sites`
- `default_resume_file`
- `market_priority`

当前支持的站点：

- `linkedin`
- `indeed`
- `zip_recruiter`

## 环境变量

- `QUICKAPPLY_CONFIG_PATH`
- `QUICKAPPLY_DATABASE_URL`
- `QUICKAPPLY_WORKSPACES_DIR`
- `QUICKAPPLY_PROXY_FILE`
- `QUICKAPPLY_CODEX_TIMEOUT_SECONDS`
- `PORT`
- `HOST`

## 代理

如果你要用轮换代理：

1. 复制 `config/proxies.example.txt`
2. 保存为 `config/proxies.local.txt`
3. 一行写一个代理
4. 需要时用 `QUICKAPPLY_PROXY_FILE` 指向它

## 数据存储

QuickApply 默认把运行时数据放在：

- `data/jobs.db`
- `data/workspaces/`

这些路径同时适合本地运行和 Docker bind mount。

---

> 继续阅读：[← 快速开始](./getting-started.zh-CN.md) · [文档首页](./README.zh-CN.md) · [下一篇：抓取与投递流程 →](./workflows.zh-CN.md)

# Tailor 精修说明

[English](./tailor.md)

> 导航：[← 抓取与投递流程](./workflows.zh-CN.md) · [文档首页](./README.zh-CN.md) · [下一篇：部署与运维 →](./deployment.zh-CN.md)

## Tailor 是什么

Tailor 是针对单个岗位的简历工作区。

它现在采用单 Session 设计：

- 一个岗位一个工作区
- 一个工作区复用同一个 Codex session
- 一个可编辑的指令面板，确认后再发送

## 工作区里的主要文件

常见文件包括：

- `role.md`
- `user_notes.md`
- `cv_template.tex`
- `resume_revision_advice.md`
- `session_instruction.md`
- `final_resume.tex`
- `final_resume.pdf`

## 修改建议

公开版 `.codex` skills 主要做两件事：

1. 生成给用户看的修改建议
2. 从建议里提炼出发给同一个 Codex session 的结构化指令

公开版当前更关注：

- 项目取舍
- 强调点控制
- proof point 整理
- 保持简历简洁且事实可信

## Session 流程

推荐循环：

1. 检查岗位工作区
2. 生成修改建议
3. 阅读 `resume_revision_advice.md`
4. 需要时编辑 `session_instruction.md`
5. 发送给同一个 Codex session
6. 查看重新编译后的 PDF

## PDF 输出

Tailor 的核心不是只改 `.tex`，而是看最终 PDF。

应用会编译：

- `final_resume.tex`
- `final_resume.pdf`

这样每一轮改动后都能直接看版面结果。

## 重要边界

- Tailor 仍然依赖你本机已经安装并登录 `codex`
- Docker 镜像不会带上你的 Codex 登录状态
- 公开仓库里的简历和 proof points 都是 synthetic 数据

---

> 继续阅读：[← 抓取与投递流程](./workflows.zh-CN.md) · [文档首页](./README.zh-CN.md) · [下一篇：部署与运维 →](./deployment.zh-CN.md)

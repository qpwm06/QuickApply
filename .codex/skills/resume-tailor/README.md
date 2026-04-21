# Resume Tailor Skills

这个目录是 Tailor Web 工作台的项目内 Codex skills。

当前只保留两条主 skill：

1. `revision_advice.md`
   - 面向用户的改稿建议
   - 同时生成结构化的 Session 指令

2. `session_send.md`
   - 把结构化 Session 指令落实到最终 `final_resume.tex`
   - 保持事实一致与 LaTeX 可编译

这些规则已经吸收了旧 `.claude/agents` 里有价值的工作习惯，但不再按多 agent 方式拆分。
项目内 `.claude` 现在只作为 legacy 参考，不再是 Tailor skill 的运行时来源。

## 适用场景

- 当前目录已经是某个 `Role` 工作区
- 工作区里至少有：
  - `role.md`
  - `user_notes.md`
  - `cv_template.tex`（或已有 final tex）

## 事实来源白名单

两条 skill 中所有推理和改稿只允许使用以下来源，不得引入外部信息：

- `role.md`
- `user_notes.md`
- 基础简历 / cv_template.tex
- `asset/ProjectLibrary/projects.md`
- `asset/Reference/reference.md`

## 统一约束

- 不允许虚构项目、论文、数据、技术栈、时间线
- 每一步 final message 控制在 1-2 句简体中文
- 只允许在当前 `Role` 工作区内写文件
- 不要修改项目内 `.codex` 或 legacy `.claude` 文件

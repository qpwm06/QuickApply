# Tailor Workflow

[简体中文](./tailor.zh-CN.md)

> Navigation: [← Workflow Tour](./workflows.md) · [Documentation Home](./README.md) · [Next: Deployment and Operations →](./deployment.md)

## What Tailor Is

Tailor is the job-specific resume workspace.

It is built around a single-session model:

- one workspace per job
- one Codex session reused across the workspace
- one editable instruction panel that you can refine before sending

## Main Workspace Files

Typical workspace artifacts include:

- `role.md`
- `user_notes.md`
- `cv_template.tex`
- `resume_revision_advice.md`
- `session_instruction.md`
- `final_resume.tex`
- `final_resume.pdf`

## Revision Advice

The public `.codex` skills do two things:

1. generate revision advice for the user
2. derive a structured session instruction for the same Codex session

The public version is tuned for:

- project selection
- emphasis control
- proof-point hygiene
- keeping the resume factual and compact

## Session Flow

Recommended loop:

1. review the job workspace
2. generate revision advice
3. inspect `resume_revision_advice.md`
4. edit `session_instruction.md` if needed
5. send it to the same Codex session
6. review the rebuilt PDF

## PDF Output

Tailor is centered on the final PDF result, not just the `.tex`.

The app compiles:

- `final_resume.tex`
- `final_resume.pdf`

That makes it easier to iterate visually after each revision round.

## Important Limits

- Tailor still requires your own local `codex` CLI
- Docker does not ship with your Codex authentication
- the public repo uses synthetic resumes and synthetic proof points

---

> Continue: [← Workflow Tour](./workflows.md) · [Documentation Home](./README.md) · [Next: Deployment and Operations →](./deployment.md)

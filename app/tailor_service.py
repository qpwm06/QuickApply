from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.asset_retriever import write_shortlist_for_workspace
from app.config import ROOT_DIR, Settings
from app.location_utils import job_country_label
from app.models import JobRecord
from app.resume_profile import ResumeProfile
from app.time_utils import LOCAL_TIMEZONE

PARENT_ROOT = ROOT_DIR.parent
CODEX_ROOT = PARENT_ROOT / ".codex"
SKILL_ROOT = CODEX_ROOT / "skills" / "resume-tailor"
PROJECT_LIBRARY_PATH = PARENT_ROOT / "asset" / "ProjectLibrary" / "projects.md"
REFERENCE_LIBRARY_PATH = PARENT_ROOT / "asset" / "Reference" / "reference.md"
TEMPLATE_SOURCE_PATH = PARENT_ROOT / "asset" / "Template" / "cv_template.tex"
SKILL_PATHS = {
    "revision_advice": SKILL_ROOT / "revision_advice.md",
    "session_send": SKILL_ROOT / "session_send.md",
}
TAILOR_SKILL_LABELS = {
    "revision_advice": "修改建议 Skill",
    "session_send": "Session 修改 Skill",
}
TAILOR_STEP_ORDER = ("setup", "matching", "tailor_loop", "final_proof", "vibe_review")
TAILOR_STEP_LABELS = {
    "setup": "Setup",
    "matching": "Role Matcher",
    "tailor_loop": "Tailor Loop",
    "final_proof": "Final Proof",
    "vibe_review": "Vibe Review",
}
TAILOR_ARTIFACT_KEYS = {
    "role": "role.md",
    "notes": "user_notes.md",
    "snapshot": "job_snapshot.json",
    "template": "cv_template.tex",
    "advice": "tailor_advice.md",
    "revision_advice": "resume_revision_advice.md",
    "session_instruction": "session_instruction.md",
    "asset_shortlist": "asset_shortlist.md",
    "matching_analysis": "matching_analysis.json",
    "tailored_resume": "cv_tailored.tex",
    "fact_check_report": "fact_check_report.json",
    "final_resume": "final_resume.tex",
    "final_pdf": "final_resume.pdf",
    "diff_tex": "diff.tex",
    "diff_pdf": "diff.pdf",
    "vibe_review": "vibe_review.md",
}
LEGACY_STEP_KEY_MAP = {
    "tailor": "tailor_loop",
    "fact_check": "tailor_loop",
    "finalize": "final_proof",
}
SESSION_FILE_PATTERN = re.compile(
    r"rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-([0-9a-f-]{36})\.jsonl$",
    re.IGNORECASE,
)
MAX_TAILOR_LOOP_ATTEMPTS = 3
REVISION_ADVICE_SECTION_HEADING = "修改建议"
SESSION_INSTRUCTION_SECTION_HEADING = "发给 Codex Session 的指令"
MD_AGENT_TARGET_LABELS = {
    "revision_advice": "修改建议摘要",
    "session_instruction": "Session Input",
}
MD_AGENT_MODE_LABELS = {
    "review": "查看",
    "optimize": "优化",
}
EMBEDDED_SHARED_SKILL_TEXT = """
你正在服务 Tailor Web 工作台，而不是旧的多 agent 编排器。

统一工作习惯：
- 复用同一个 Codex session，不要把每次修改拆成新的会话。
- role.md 是岗位主输入；job_snapshot.json 只留档，不是主要推理来源。
- 事实来源只允许：role.md、user_notes.md、基础简历、projects.md、reference.md。
- 不允许虚构项目经历、论文状态、结果数字、职责边界或岗位要求。
- 优先做删减、压缩、前置和重排，尽量保留原简历结构，方便用户继续手改。
- 当前已有的 \\underline{} 只能分析是否合理，不能自动扩写或引入新的未经证实强调点。
- 涉及 publications / references 时，必须显式核对 Google Scholar、Selected Publications 和 reference.md 的最新状态。
- 如果用户意图与事实来源冲突，以事实来源为准，并在输出中保守处理。
- 最终输出要短、可执行、可编译，避免宏观空话和重复分析。
- 简历正文（tex 文件中的可见内容）必须全部用英文撰写，中文只用于 final message 和 Markdown 工作文件。
- 每个项目的 bullet 总数控制在 3-6 条以内；如果 bullet 超过 6 条，先删减到 6 条以内再优化措辞。
- 修改建议类输出控制在 800 字以内；Session 指令类输出控制在 500 字以内。
""".strip()

EMBEDDED_STEP_RULE_TEXTS = {
    "setup": """
本步骤只负责确认上下文，不做内容修改。
- 确认 role、notes、基础模板和最终稿路径。
- 不生成额外文件，不改 workspace 内容。
- 输出要短，明确后续继续复用同一个 session。
""".strip(),
    "matching": """
本步骤只做岗位-项目匹配与改稿方向判断。
- 先判断岗位真正看重的研究问题、方法栈和业务语境。
- 项目组合控制在 2-4 条主线，优先高相关、高可证实、高迁移价值。
- 不进入逐段改写，不泛泛重述 role.md。
""".strip(),
    "md_advice_manager": """
本步骤只处理 Markdown 工作文件。
- 目标是让文件更清楚、更短、更可执行。
- review 模式只指出问题，不替用户改原文。
- optimize 模式只重写目标输出文件，不碰源文件。
""".strip(),
    "content_tailor": """
本步骤只改简历内容本身。
- 优先删减、压缩、前置、重排，不做花哨扩写。
- 项目 bullet 要围绕岗位相关性组织，不要列流水账。
- 保持 LaTeX 结构稳定，方便用户继续手改。
""".strip(),
    "fact_check": """
本步骤只做事实核验。
- 逐条检查项目、论文状态、数字、职责边界和关键词映射。
- 发现问题时给出来源真相与可执行修复建议。
- 不直接修改 tex，避免把判断和改写混在一起。
""".strip(),
    "final_proof": """
本步骤只产出最终 tex。
- 吸收前面已经确认的问题修复，不再做大范围岗位分析。
- 优先保证事实一致、结构稳定、LaTeX 可编译。
- references / publications 可以保守修正，但不要虚构状态。
""".strip(),
    "vibe_review": """
本步骤做最终整体润色。
- 关注整份 CV 的叙事张力、重点排序、冗余和不协调表达。
- 可以顺手修正 proofreader 层面的语言问题，但不能突破事实边界。
- 输出除了改 final tex，还要给出简短复盘，便于下一轮 vibe 微调。
""".strip(),
}


class TailorStepStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class TailorWorkspace:
    workspace_dir: Path
    workspace_label: str
    state_path: Path
    pipeline_state_path: Path
    snapshot_path: Path
    role_path: Path
    notes_path: Path
    base_resume_copy_path: Path
    advice_path: Path
    revision_advice_path: Path
    session_instruction_path: Path
    asset_shortlist_path: Path
    matching_analysis_path: Path
    tailored_resume_path: Path
    fact_check_report_path: Path
    final_resume_path: Path
    final_resume_pdf_path: Path
    diff_path: Path
    diff_pdf_path: Path
    vibe_review_path: Path
    step_logs: dict[str, Path]
    step_message_files: dict[str, Path]
    step_prompt_files: dict[str, Path]
    action_logs: dict[str, Path]
    action_message_files: dict[str, Path]
    action_prompt_files: dict[str, Path]
    base_resume_path: str
    role_markdown: str
    user_notes: str
    template_text: str
    advice_text: str
    revision_advice_text: str
    session_instruction_text: str
    asset_shortlist_text: str
    matching_analysis_text: str
    tailored_resume_text: str
    fact_check_text: str
    final_resume_text: str
    diff_text: str
    vibe_review_text: str
    pipeline_state: dict[str, object]


def _safe_json_load(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json_pretty(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return path.read_text(encoding="utf-8")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _role_segment(value: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", value.strip())
    if not tokens:
        return "Item"

    parts: list[str] = []
    for token in tokens:
        if token.isupper() and len(token) <= 4:
            parts.append(token)
        else:
            parts.append(token[0].upper() + token[1:])
    return "".join(parts)


def _workspace_label(workspace_dir: Path) -> str:
    try:
        return str(workspace_dir.relative_to(PARENT_ROOT))
    except ValueError:
        return str(workspace_dir)


def _resume_source_path(relative_path: str) -> Path:
    return (ROOT_DIR / relative_path).resolve()


def _default_resume_for_profile(
    profile_slug: str,
    settings: Settings,
    resume_profile: ResumeProfile,
) -> str:
    for profile in settings.search_profiles:
        if profile.slug == profile_slug and profile.default_resume_file:
            return profile.default_resume_file
    return resume_profile.source_files[0]


def _build_role_markdown(job: JobRecord) -> str:
    description = job.description.strip() or "暂无完整职位描述。"
    location_text = job.location_text or ", ".join(
        part for part in [job.city, job.state, job.country] if part
    )
    return "\n".join(
        [
            f"# {job.title}",
            "",
            "## Meta",
            f"- Company: {job.company}",
            f"- Profile: {job.profile_label}",
            f"- Source: {job.source_site}",
            f"- Country Filter: {job_country_label(job)}",
            f"- Location: {location_text or 'N/A'}",
            f"- Job URL: {job.job_url or 'N/A'}",
            "",
            "## Original Description",
            description,
            "",
            "## Tailoring Focus",
            "- 你可以在这里补充希望强调或回避的点。",
        ]
    ).strip() + "\n"


def _default_notes_markdown() -> str:
    return "\n".join(
        [
            "# User Notes",
            "",
            "- 重点突出：",
            "- 想淡化：",
            "- 额外背景：",
            "- 目标公司/组别偏好：",
        ]
    ).strip() + "\n"


def _safe_relative_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


_MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def extract_markdown_section(markdown_text: str, heading: str) -> str:
    lines = (markdown_text or "").splitlines()
    target_heading = _normalize_heading(heading)
    start_index: int | None = None
    heading_level = 0

    for index, line in enumerate(lines):
        matched = _MARKDOWN_HEADING_PATTERN.match(line)
        if not matched:
            continue
        if _normalize_heading(matched.group(2)) != target_heading:
            continue
        start_index = index + 1
        heading_level = len(matched.group(1))
        break

    if start_index is None:
        return ""

    end_index = len(lines)
    for index in range(start_index, len(lines)):
        matched = _MARKDOWN_HEADING_PATTERN.match(lines[index])
        if matched and len(matched.group(1)) <= heading_level:
            end_index = index
            break
    return "\n".join(lines[start_index:end_index]).strip()


def remove_markdown_section(markdown_text: str, heading: str) -> str:
    lines = (markdown_text or "").splitlines()
    target_heading = _normalize_heading(heading)
    start_index: int | None = None
    heading_level = 0

    for index, line in enumerate(lines):
        matched = _MARKDOWN_HEADING_PATTERN.match(line)
        if not matched:
            continue
        if _normalize_heading(matched.group(2)) != target_heading:
            continue
        start_index = index
        heading_level = len(matched.group(1))
        break

    if start_index is None:
        return markdown_text.strip()

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        matched = _MARKDOWN_HEADING_PATTERN.match(lines[index])
        if matched and len(matched.group(1)) <= heading_level:
            end_index = index
            break

    trimmed_lines = lines[:start_index] + lines[end_index:]
    return "\n".join(trimmed_lines).strip()


def split_revision_advice(markdown_text: str) -> tuple[str, str]:
    summary_text = remove_markdown_section(markdown_text, SESSION_INSTRUCTION_SECTION_HEADING)
    session_instruction_text = extract_markdown_section(
        markdown_text,
        SESSION_INSTRUCTION_SECTION_HEADING,
    )
    return summary_text.strip(), session_instruction_text.strip()


def _extract_google_scholar_url(template_text: str) -> str:
    matched = re.search(r"https://scholar\.google\.com/[^\s}]+", template_text)
    return matched.group(0) if matched else ""


def _extract_underlined_phrases(template_text: str, *, limit: int = 12) -> list[str]:
    phrases: list[str] = []
    for matched in re.finditer(r"\\underline\{([^{}]+)\}", template_text):
        phrase = re.sub(r"\s+", " ", matched.group(1).strip())
        if not phrase or phrase in phrases:
            continue
        phrases.append(phrase)
        if len(phrases) >= limit:
            break
    return phrases


def _extract_publication_lines(template_text: str, *, limit: int = 6) -> list[str]:
    lines = template_text.splitlines()
    in_publication_block = False
    publication_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not in_publication_block and "Selected Publications" in line:
            in_publication_block = True
            continue
        if not in_publication_block:
            continue
        if line.startswith(r"\section*") and "Selected Publications" not in line:
            break
        if line.startswith(r"\subsection*"):
            break
        if line.startswith(r"\item "):
            publication_lines.append(line[6:].strip())
            if len(publication_lines) >= limit:
                break
    return publication_lines


def _extract_reference_status_lines(reference_text: str, *, limit: int = 8) -> list[str]:
    status_keywords = ("accepted", "under review", "under revision", "biorxiv", "advance article")
    lines: list[str] = []
    for raw_line in reference_text.splitlines():
        normalized = raw_line.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(keyword in lowered for keyword in status_keywords):
            lines.append(normalized)
            if len(lines) >= limit:
                break
    return lines


class TailorService:
    def __init__(self, settings: Settings, resume_profile: ResumeProfile) -> None:
        self.settings = settings
        self.resume_profile = resume_profile
        self.step_rule_texts = dict(EMBEDDED_STEP_RULE_TEXTS)
        self.skill_texts = {
            key: _read_text(path)
            for key, path in SKILL_PATHS.items()
        }

    @property
    def workspace_root(self) -> Path:
        raw_path = Path(self.settings.app.workspaces_dir)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (ROOT_DIR / raw_path).resolve()

    def available_resume_files(self) -> list[str]:
        return sorted(dict.fromkeys(self.resume_profile.source_files))

    def skill_path(self, skill_key: str) -> Path | None:
        return SKILL_PATHS.get(skill_key)

    def skill_label(self, skill_key: str) -> str:
        return TAILOR_SKILL_LABELS.get(skill_key, skill_key)

    def skill_text(self, skill_key: str) -> str:
        return self.skill_texts.get(skill_key, "")

    def skill_items(self) -> list[tuple[str, Path]]:
        return [
            (skill_key, path)
            for skill_key, path in SKILL_PATHS.items()
        ]

    def revision_resume_source(self, workspace: TailorWorkspace) -> tuple[Path, str, bool]:
        final_resume_text = workspace.final_resume_text
        if not final_resume_text and workspace.final_resume_path.exists():
            final_resume_text = _read_text(workspace.final_resume_path)
        if final_resume_text.strip():
            return workspace.final_resume_path, final_resume_text, True

        template_text = workspace.template_text
        if not template_text and workspace.base_resume_copy_path.exists():
            template_text = _read_text(workspace.base_resume_copy_path)
        return workspace.base_resume_copy_path, template_text, False

    def md_agent_source_path(self, workspace: TailorWorkspace, target_key: str) -> Path:
        if target_key == "revision_advice":
            return workspace.revision_advice_path
        if target_key == "session_instruction":
            return workspace.session_instruction_path
        raise ValueError(f"unsupported md agent target: {target_key}")

    def md_agent_result_path(self, workspace: TailorWorkspace, target_key: str, mode: str) -> Path:
        if mode not in MD_AGENT_MODE_LABELS:
            raise ValueError(f"unsupported md agent mode: {mode}")
        source_path = self.md_agent_source_path(workspace, target_key)
        suffix = "agent_review" if mode == "review" else "agent_optimized"
        return source_path.with_name(f"{source_path.stem}.{suffix}.md")

    def _build_revision_signal_block(self, workspace: TailorWorkspace) -> str:
        source_path, resume_text, uses_final_resume = self.revision_resume_source(workspace)
        reference_text = _read_text(REFERENCE_LIBRARY_PATH)
        scholar_url = _extract_google_scholar_url(resume_text)
        underlined_phrases = _extract_underlined_phrases(resume_text)
        publication_lines = _extract_publication_lines(resume_text)
        reference_status_lines = _extract_reference_status_lines(reference_text)

        lines = [
            "当前简历与文献信号:",
            f"- 当前简历来源: {'final tex' if uses_final_resume else '模板副本回退'}",
            f"- 当前读取文件: {source_path}",
            f"- Google Scholar 链接: {scholar_url or '未发现'}",
            "- 当前简历里已有的 underline 强调点:",
        ]
        if underlined_phrases:
            lines.extend(f"  - {phrase}" for phrase in underlined_phrases)
        else:
            lines.append("  - 未发现")

        lines.append("- 当前简历里 Selected Publications 区块:")
        if publication_lines:
            lines.extend(f"  - {line}" for line in publication_lines)
        else:
            lines.append("  - 未发现")

        lines.append("- reference.md 中带状态的最新条目:")
        if reference_status_lines:
            lines.extend(f"  - {line}" for line in reference_status_lines)
        else:
            lines.append("  - 未发现")

        return "\n".join(lines)

    def _sync_session_instruction_artifact(
        self,
        *,
        revision_advice_path: Path,
        session_instruction_path: Path,
    ) -> None:
        if not revision_advice_path.exists():
            return

        revision_advice_text = _read_text(revision_advice_path)
        _, extracted_instruction = split_revision_advice(revision_advice_text)
        if not extracted_instruction:
            return

        should_write = not session_instruction_path.exists()
        if session_instruction_path.exists():
            try:
                should_write = (
                    revision_advice_path.stat().st_mtime_ns
                    >= session_instruction_path.stat().st_mtime_ns
                )
            except OSError:
                should_write = True

        if should_write:
            session_instruction_path.write_text(
                extracted_instruction.strip() + "\n",
                encoding="utf-8",
            )

    def ensure_workspace(self, job: JobRecord) -> TailorWorkspace:
        workspace_root = self.workspace_root
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_dir = self._resolve_workspace_dir_for_job(workspace_root, job)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        state_path = workspace_dir / "workspace_state.json"
        pipeline_state_path = workspace_dir / "pipeline_state.json"
        snapshot_path = workspace_dir / "job_snapshot.json"
        role_path = workspace_dir / TAILOR_ARTIFACT_KEYS["role"]
        notes_path = workspace_dir / TAILOR_ARTIFACT_KEYS["notes"]
        template_path = workspace_dir / TAILOR_ARTIFACT_KEYS["template"]
        advice_path = workspace_dir / TAILOR_ARTIFACT_KEYS["advice"]
        revision_advice_path = workspace_dir / TAILOR_ARTIFACT_KEYS["revision_advice"]
        session_instruction_path = workspace_dir / TAILOR_ARTIFACT_KEYS["session_instruction"]
        asset_shortlist_path = workspace_dir / TAILOR_ARTIFACT_KEYS["asset_shortlist"]
        matching_analysis_path = workspace_dir / TAILOR_ARTIFACT_KEYS["matching_analysis"]
        tailored_resume_path = workspace_dir / TAILOR_ARTIFACT_KEYS["tailored_resume"]
        fact_check_report_path = workspace_dir / TAILOR_ARTIFACT_KEYS["fact_check_report"]
        final_resume_path = workspace_dir / self._final_resume_filename(job, workspace_dir)
        final_resume_pdf_path = final_resume_path.with_suffix(".pdf")
        diff_path = workspace_dir / TAILOR_ARTIFACT_KEYS["diff_tex"]
        diff_pdf_path = workspace_dir / TAILOR_ARTIFACT_KEYS["diff_pdf"]
        vibe_review_path = workspace_dir / TAILOR_ARTIFACT_KEYS["vibe_review"]
        step_logs = {
            step_key: workspace_dir / f"{step_key}.log"
            for step_key in TAILOR_STEP_ORDER
        }
        step_message_files = {
            step_key: workspace_dir / f"{step_key}_last_message.md"
            for step_key in TAILOR_STEP_ORDER
        }
        step_prompt_files = {
            step_key: workspace_dir / f"{step_key}.prompt.md"
            for step_key in TAILOR_STEP_ORDER
        }
        action_logs = {
            "advice": workspace_dir / "advice.log",
            "revision_advice": workspace_dir / "revision_advice.log",
            "md_agent": workspace_dir / "md_agent.log",
            "session_start": workspace_dir / "session_start.log",
            "session_prompt": workspace_dir / "session_prompt.log",
        }
        action_message_files = {
            "advice": workspace_dir / "advice_last_message.md",
            "revision_advice": workspace_dir / "revision_advice_last_message.md",
            "md_agent": workspace_dir / "md_agent_last_message.md",
            "session_start": workspace_dir / "session_start_last_message.md",
            "session_prompt": workspace_dir / "session_prompt_last_message.md",
        }
        action_prompt_files = {
            "advice": workspace_dir / "advice.prompt.md",
            "revision_advice": workspace_dir / "revision_advice.prompt.md",
            "md_agent": workspace_dir / "md_agent.prompt.md",
            "session_start": workspace_dir / "session_start.prompt.md",
            "session_prompt": workspace_dir / "session_prompt.prompt.md",
        }

        state = _safe_json_load(state_path)
        selected_resume_path = str(
            state.get("selected_resume_path")
            or _default_resume_for_profile(
                job.profile_slug,
                self.settings,
                self.resume_profile,
            )
        )
        state_payload = {
            "job_id": job.id,
            "unique_key": job.unique_key,
            "job_url": job.job_url,
            "selected_resume_path": selected_resume_path,
            "created_at": state.get("created_at") or datetime.now(timezone.utc).isoformat(),
        }

        snapshot_payload = {
            "job_id": job.id,
            "unique_key": job.unique_key,
            "title": job.title,
            "company": job.company,
            "profile_slug": job.profile_slug,
            "profile_label": job.profile_label,
            "source_site": job.source_site,
            "location_text": job.location_text,
            "city": job.city,
            "state": job.state,
            "country": job.country,
            "job_url": job.job_url,
            "score": job.score,
            "description": job.description,
        }
        snapshot_path.write_text(
            json.dumps(snapshot_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if not role_path.exists():
            role_path.write_text(_build_role_markdown(job), encoding="utf-8")
        if not notes_path.exists():
            notes_path.write_text(_default_notes_markdown(), encoding="utf-8")
        self._copy_resume_source(selected_resume_path, template_path)
        self._sync_session_instruction_artifact(
            revision_advice_path=revision_advice_path,
            session_instruction_path=session_instruction_path,
        )
        state_path.write_text(
            json.dumps(state_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        pipeline_state = self._normalize_pipeline_state(
            _safe_json_load(pipeline_state_path),
            workspace_dir=workspace_dir,
            selected_resume_path=selected_resume_path,
            final_resume_name=final_resume_path.name,
        )
        if not pipeline_state.get("asset_baseline_mtime_ns"):
            pipeline_state["asset_baseline_mtime_ns"] = self._current_asset_mtime_ns()
        pipeline_state_path.write_text(
            json.dumps(pipeline_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return TailorWorkspace(
            workspace_dir=workspace_dir,
            workspace_label=_workspace_label(workspace_dir),
            state_path=state_path,
            pipeline_state_path=pipeline_state_path,
            snapshot_path=snapshot_path,
            role_path=role_path,
            notes_path=notes_path,
            base_resume_copy_path=template_path,
            advice_path=advice_path,
            revision_advice_path=revision_advice_path,
            session_instruction_path=session_instruction_path,
            asset_shortlist_path=asset_shortlist_path,
            matching_analysis_path=matching_analysis_path,
            tailored_resume_path=tailored_resume_path,
            fact_check_report_path=fact_check_report_path,
            final_resume_path=final_resume_path,
            final_resume_pdf_path=final_resume_pdf_path,
            diff_path=diff_path,
            diff_pdf_path=diff_pdf_path,
            vibe_review_path=vibe_review_path,
            step_logs=step_logs,
            step_message_files=step_message_files,
            step_prompt_files=step_prompt_files,
            action_logs=action_logs,
            action_message_files=action_message_files,
            action_prompt_files=action_prompt_files,
            base_resume_path=selected_resume_path,
            role_markdown=_read_text(role_path),
            user_notes=_read_text(notes_path),
            template_text=_read_text(template_path),
            advice_text=_read_text(advice_path),
            revision_advice_text=_read_text(revision_advice_path),
            session_instruction_text=_read_text(session_instruction_path),
            asset_shortlist_text=_read_text(asset_shortlist_path),
            matching_analysis_text=_read_json_pretty(matching_analysis_path),
            tailored_resume_text=_read_text(tailored_resume_path),
            fact_check_text=_read_json_pretty(fact_check_report_path),
            final_resume_text=_read_text(final_resume_path),
            diff_text=_read_text(diff_path),
            vibe_review_text=_read_text(vibe_review_path),
            pipeline_state=pipeline_state,
        )

    def save_workspace(
        self,
        job: JobRecord,
        *,
        base_resume_path: str,
        role_markdown: str,
        user_notes: str,
        session_instruction_text: str | None = None,
    ) -> TailorWorkspace:
        workspace = self.ensure_workspace(job)
        previous_resume_path = workspace.base_resume_path
        normalized_resume_path = base_resume_path or workspace.base_resume_path
        workspace.role_path.write_text(role_markdown.strip() + "\n", encoding="utf-8")
        workspace.notes_path.write_text(user_notes.strip() + "\n", encoding="utf-8")
        if session_instruction_text is not None:
            cleaned_instruction = session_instruction_text.strip()
            if cleaned_instruction:
                workspace.session_instruction_path.write_text(
                    cleaned_instruction + "\n",
                    encoding="utf-8",
                )
            else:
                workspace.session_instruction_path.write_text("", encoding="utf-8")
        self._copy_resume_source(normalized_resume_path, workspace.base_resume_copy_path)

        state_payload = _safe_json_load(workspace.state_path)
        state_payload["selected_resume_path"] = normalized_resume_path
        workspace.state_path.write_text(
            json.dumps(state_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        pipeline_state = self._load_pipeline_state(workspace)
        resume_changed = previous_resume_path != normalized_resume_path
        pipeline_state["selected_resume_path"] = normalized_resume_path
        if pipeline_state.get("advice_status") == "succeeded":
            pipeline_state["advice_status"] = "stale"
        if pipeline_state.get("revision_advice_status") == "succeeded":
            pipeline_state["revision_advice_status"] = "stale"
        pipeline_state["advice_error"] = ""
        pipeline_state["advice_message"] = (
            "工作区已更新，建议重新生成流程建议。"
        )
        pipeline_state["revision_advice_error"] = ""
        pipeline_state["revision_advice_message"] = (
            "工作区已更新，建议重新生成修改建议。"
        )
        if resume_changed:
            # 中文注释：用户切换模板时，直接把最终稿重置到新模板，避免 session 继续改旧模板。
            self._copy_resume_source(normalized_resume_path, workspace.final_resume_path)
            pipeline_state["session_id"] = ""
            pipeline_state["session_status"] = "not_started"
            pipeline_state["session_established_at"] = None
            pipeline_state["session_error"] = ""
            try:
                self._compile_pdf(workspace.final_resume_path)
                self._ensure_diff_pdf(workspace)
            except Exception:
                pass
        self._mark_steps_pending_from(
            pipeline_state,
            "matching",
            "工作区内容已更新，等待重新运行。",
        )
        if not workspace.final_resume_path.exists():
            self._copy_resume_source(normalized_resume_path, workspace.final_resume_path)
        self._save_pipeline_state(workspace, pipeline_state)
        return self.ensure_workspace(job)

    def save_session_instruction(
        self,
        job: JobRecord,
        *,
        instruction_text: str,
    ) -> TailorWorkspace:
        workspace = self.ensure_workspace(job)
        cleaned_instruction = instruction_text.strip()
        workspace.session_instruction_path.write_text(
            (cleaned_instruction + "\n") if cleaned_instruction else "",
            encoding="utf-8",
        )
        return self.ensure_workspace(job)

    def save_tailored_resume(self, job: JobRecord, latex_text: str) -> TailorWorkspace:
        workspace = self.ensure_workspace(job)
        workspace.tailored_resume_path.write_text(latex_text, encoding="utf-8")
        pipeline_state = self._load_pipeline_state(workspace)
        self._mark_steps_pending_from(
            pipeline_state,
            "tailor_loop",
            "cv_tailored.tex 已人工修改，建议重新运行 Tailor Loop。",
        )
        self._save_pipeline_state(workspace, pipeline_state)
        return self.ensure_workspace(job)

    def save_final_resume(self, job: JobRecord, latex_text: str) -> TailorWorkspace:
        workspace = self.ensure_workspace(job)
        workspace.final_resume_path.write_text(latex_text, encoding="utf-8")
        self._compile_pdf(workspace.final_resume_path)
        self._ensure_diff_pdf(workspace)

        pipeline_state = self._load_pipeline_state(workspace)
        final_step = self._get_step_record(pipeline_state, "final_proof")
        final_step["status"] = "succeeded"
        final_step["error_text"] = ""
        final_step["message"] = "已人工保存 final tex 并重新编译 PDF。"
        final_step["finished_at"] = datetime.now(timezone.utc).isoformat()
        self._mark_steps_pending_from(
            pipeline_state,
            "vibe_review",
            "final tex 已人工修改，等待重新做 Vibe Review。",
        )
        self._save_pipeline_state(workspace, pipeline_state)
        return self.ensure_workspace(job)

    def ensure_final_resume_seed(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        reset_from_template: bool = False,
    ) -> tuple[bool, str]:
        seeded = False
        compile_message = ""
        if reset_from_template or not workspace.final_resume_path.exists():
            seeded = True
            self._copy_resume_source(workspace.base_resume_path, workspace.final_resume_path)
        try:
            self._compile_pdf(workspace.final_resume_path)
            self._ensure_diff_pdf(workspace)
        except Exception as exc:
            compile_message = str(exc)
        return seeded, compile_message

    def run_advice(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> str:
        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["advice_status"] = "running"
        pipeline_state["advice_error"] = ""
        pipeline_state["advice_message"] = "正在生成流程建议。"
        self._save_pipeline_state(workspace, pipeline_state)

        try:
            message, _ = self._run_workspace_action(
                action_key="advice",
                title="Advice",
                workspace=workspace,
                prompt=self._build_advice_prompt(job, workspace),
                expected_paths=[workspace.advice_path],
                session_id="",
                pid_callback=pid_callback,
            )
        except Exception as exc:
            pipeline_state = self._load_pipeline_state(workspace)
            pipeline_state["advice_status"] = "failed"
            pipeline_state["advice_error"] = str(exc)
            pipeline_state["advice_message"] = str(exc)
            self._save_pipeline_state(workspace, pipeline_state)
            raise

        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["advice_status"] = "succeeded"
        pipeline_state["advice_error"] = ""
        pipeline_state["advice_message"] = message
        pipeline_state["advice_updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_pipeline_state(workspace, pipeline_state)
        return message

    def run_revision_advice(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> str:
        cleaned_session_id = session_id.strip()
        if not cleaned_session_id:
            raise RuntimeError("当前没有可复用的 Codex session，无法在同一 Session 中生成修改建议。")

        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["revision_advice_status"] = "running"
        pipeline_state["revision_advice_error"] = ""
        pipeline_state["revision_advice_message"] = "正在生成修改建议。"
        pipeline_state["session_id"] = cleaned_session_id
        pipeline_state["session_status"] = "ready"
        pipeline_state["session_error"] = ""
        self._save_pipeline_state(workspace, pipeline_state)

        try:
            message, next_session_id = self._run_workspace_action(
                action_key="revision_advice",
                title="Revision Advice",
                workspace=workspace,
                prompt=self._build_revision_advice_prompt(job, workspace),
                expected_paths=[workspace.revision_advice_path],
                session_id=cleaned_session_id,
                pid_callback=pid_callback,
            )
        except Exception as exc:
            pipeline_state = self._load_pipeline_state(workspace)
            pipeline_state["revision_advice_status"] = "failed"
            pipeline_state["revision_advice_error"] = str(exc)
            pipeline_state["revision_advice_message"] = str(exc)
            self._save_pipeline_state(workspace, pipeline_state)
            raise

        self._sync_session_instruction_artifact(
            revision_advice_path=workspace.revision_advice_path,
            session_instruction_path=workspace.session_instruction_path,
        )
        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["revision_advice_status"] = "succeeded"
        pipeline_state["revision_advice_error"] = ""
        pipeline_state["revision_advice_message"] = message
        pipeline_state["revision_advice_updated_at"] = datetime.now(timezone.utc).isoformat()
        pipeline_state["session_id"] = next_session_id or cleaned_session_id
        pipeline_state["session_status"] = "ready"
        pipeline_state["session_error"] = ""
        self._save_pipeline_state(workspace, pipeline_state)
        return message

    def run_md_agent(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        target_key: str,
        mode: str,
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> str:
        source_path = self.md_agent_source_path(workspace, target_key)
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在：{source_path.name}")
        result_path = self.md_agent_result_path(workspace, target_key, mode)

        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["md_agent_status"] = "running"
        pipeline_state["md_agent_target"] = target_key
        pipeline_state["md_agent_mode"] = mode
        pipeline_state["md_agent_error"] = ""
        pipeline_state["md_agent_message"] = (
            f"正在用 Agent {MD_AGENT_MODE_LABELS[mode]} {source_path.name}。"
        )
        self._save_pipeline_state(workspace, pipeline_state)

        try:
            message, _ = self._run_workspace_action(
                action_key="md_agent",
                title=f"MD Agent {MD_AGENT_MODE_LABELS[mode]}",
                workspace=workspace,
                prompt=self._build_md_agent_prompt(
                    job,
                    workspace,
                    target_key=target_key,
                    mode=mode,
                    source_path=source_path,
                    result_path=result_path,
                ),
                expected_paths=[result_path],
                session_id="",
                pid_callback=pid_callback,
            )
        except Exception as exc:
            pipeline_state = self._load_pipeline_state(workspace)
            pipeline_state["md_agent_status"] = "failed"
            pipeline_state["md_agent_target"] = target_key
            pipeline_state["md_agent_mode"] = mode
            pipeline_state["md_agent_error"] = str(exc)
            pipeline_state["md_agent_message"] = str(exc)
            self._save_pipeline_state(workspace, pipeline_state)
            raise

        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["md_agent_status"] = "succeeded"
        pipeline_state["md_agent_target"] = target_key
        pipeline_state["md_agent_mode"] = mode
        pipeline_state["md_agent_error"] = ""
        pipeline_state["md_agent_message"] = message
        pipeline_state["md_agent_updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_pipeline_state(workspace, pipeline_state)
        return message

    def start_session(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        session_id: str = "",
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> tuple[str, str]:
        pipeline_state = self._load_pipeline_state(workspace)
        seeded, compile_message = self.ensure_final_resume_seed(job, workspace)
        pipeline_state["session_status"] = "establishing"
        pipeline_state["session_error"] = ""
        self._save_pipeline_state(workspace, pipeline_state)

        try:
            message, next_session_id = self._run_workspace_action(
                action_key="session_start",
                title="Session Start",
                workspace=workspace,
                prompt=self._build_session_start_prompt(job, workspace),
                expected_paths=[workspace.final_resume_path],
                session_id=session_id,
                pid_callback=pid_callback,
            )
        except Exception as exc:
            pipeline_state = self._load_pipeline_state(workspace)
            pipeline_state["session_status"] = "failed"
            pipeline_state["session_error"] = str(exc)
            self._save_pipeline_state(workspace, pipeline_state)
            raise

        if not next_session_id.strip():
            raise RuntimeError("Session Start 已执行，但没有拿到 Codex session id。")

        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["session_id"] = next_session_id
        pipeline_state["session_status"] = "ready"
        pipeline_state["session_error"] = ""
        pipeline_state["session_established_at"] = datetime.now(timezone.utc).isoformat()
        self._save_pipeline_state(workspace, pipeline_state)

        extra_parts: list[str] = []
        if seeded:
            extra_parts.append("已把当前模板复制到 final tex。")
        if compile_message:
            extra_parts.append(f"初始 PDF 暂未编译成功：{compile_message}")
        extra_suffix = f" {' '.join(extra_parts)}" if extra_parts else ""
        return f"{message}{extra_suffix}".strip(), next_session_id

    def run_session_prompt(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        instruction_text: str,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> tuple[str, str]:
        cleaned_instruction = instruction_text.strip()
        if not cleaned_instruction:
            raise RuntimeError("Session 指令不能为空")
        if not session_id.strip():
            raise RuntimeError("当前没有可复用的 Codex session")

        self.ensure_final_resume_seed(job, workspace)
        message, next_session_id = self._run_workspace_action(
            action_key="session_prompt",
            title="Session Prompt",
            workspace=workspace,
            prompt=self._build_session_prompt_instruction(job, workspace, cleaned_instruction),
            expected_paths=[workspace.final_resume_path],
            session_id=session_id,
            pid_callback=pid_callback,
        )
        self._compile_pdf(workspace.final_resume_path)
        self._ensure_diff_pdf(workspace)

        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["session_id"] = next_session_id or session_id
        pipeline_state["session_status"] = "ready"
        pipeline_state["session_error"] = ""
        self._save_pipeline_state(workspace, pipeline_state)

        effective_session_id = next_session_id or session_id
        return (
            f"{message} 已重新编译 {workspace.final_resume_pdf_path.name} 与 {workspace.diff_pdf_path.name}。",
            effective_session_id,
        )

    def delete_workspace(self, workspace_dir: str | Path) -> bool:
        candidate = Path(workspace_dir).resolve()
        root = self.workspace_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        if not candidate.exists():
            return False
        shutil.rmtree(candidate)
        return True

    def history_dir_for_run(self, workspace: TailorWorkspace, run_id: int) -> Path:
        return workspace.workspace_dir / "history" / str(run_id)

    def has_run_snapshot(self, workspace: TailorWorkspace, run_id: int) -> bool:
        if run_id <= 0:
            return False
        history_dir = self.history_dir_for_run(workspace, run_id)
        if not history_dir.exists():
            return False
        return (history_dir / "pipeline_state.json").exists()

    def snapshot_run_history(
        self, workspace: TailorWorkspace, run_id: int
    ) -> Path | None:
        # 中文注释：把当前 final tex / PDF / pipeline_state.json 拷贝到 history/<run_id>/，
        # 便于后续回滚到该次 run 的最终稿。final_resume.tex 不存在时跳过快照。
        if run_id <= 0:
            return None
        if not workspace.final_resume_path.exists():
            return None
        history_dir = self.history_dir_for_run(workspace, run_id)
        history_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            workspace.final_resume_path,
            history_dir / workspace.final_resume_path.name,
        )
        if workspace.final_resume_pdf_path.exists():
            shutil.copy2(
                workspace.final_resume_pdf_path,
                history_dir / workspace.final_resume_pdf_path.name,
            )
        if workspace.pipeline_state_path.exists():
            shutil.copy2(
                workspace.pipeline_state_path,
                history_dir / "pipeline_state.json",
            )
        return history_dir

    def restore_run_snapshot(
        self, workspace: TailorWorkspace, run_id: int
    ) -> bool:
        history_dir = self.history_dir_for_run(workspace, run_id)
        if not history_dir.exists():
            return False
        snapshot_resume = history_dir / workspace.final_resume_path.name
        snapshot_state = history_dir / "pipeline_state.json"
        if not snapshot_resume.exists() or not snapshot_state.exists():
            return False
        shutil.copy2(snapshot_resume, workspace.final_resume_path)
        snapshot_pdf = history_dir / workspace.final_resume_pdf_path.name
        if snapshot_pdf.exists():
            shutil.copy2(snapshot_pdf, workspace.final_resume_pdf_path)
        shutil.copy2(snapshot_state, workspace.pipeline_state_path)
        try:
            self._compile_pdf(workspace.final_resume_path)
        except Exception:
            # 中文注释：若编译失败，保留拷回的 .tex 与 .pdf 副本即可，错误以 log 形式留存。
            pass
        return True

    def artifact_path(self, workspace: TailorWorkspace, artifact_key: str) -> Path | None:
        artifacts = {
            "role": workspace.role_path,
            "notes": workspace.notes_path,
            "snapshot": workspace.snapshot_path,
            "template": workspace.base_resume_copy_path,
            "advice": workspace.advice_path,
            "revision_advice": workspace.revision_advice_path,
            "session_instruction": workspace.session_instruction_path,
            "matching_analysis": workspace.matching_analysis_path,
            "tailored_resume": workspace.tailored_resume_path,
            "fact_check_report": workspace.fact_check_report_path,
            "final_resume": workspace.final_resume_path,
            "final_pdf": workspace.final_resume_pdf_path,
            "diff_tex": workspace.diff_path,
            "diff_pdf": workspace.diff_pdf_path,
            "vibe_review": workspace.vibe_review_path,
        }
        return artifacts.get(artifact_key)

    def _build_md_agent_prompt(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        target_key: str,
        mode: str,
        source_path: Path,
        result_path: Path,
    ) -> str:
        target_label = MD_AGENT_TARGET_LABELS[target_key]
        mode_label = MD_AGENT_MODE_LABELS[mode]
        optional_context = ""
        if target_key == "revision_advice":
            optional_context = (
                f"补充上下文文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
                f"- {workspace.final_resume_path}\n- {PROJECT_LIBRARY_PATH}\n- {REFERENCE_LIBRARY_PATH}\n\n"
            )
        elif target_key == "session_instruction":
            optional_context = (
                f"补充上下文文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
                f"- {workspace.revision_advice_path}\n- {workspace.final_resume_path}\n\n"
            )
        instructions = (
            f"本步骤目标：用一个轻量 agent 对 `{target_label}` 进行 `{mode_label}`。\n"
            f"岗位：{job.title} @ {job.company}\n"
            f"输入文件:\n- {source_path}\n\n"
            f"{optional_context}"
            f"输出文件:\n- {result_path}\n\n"
            "硬约束:\n"
            "1. 不要修改输入文件本身。\n"
            "2. 只写输出文件。\n"
            "3. 不要虚构任何岗位事实、项目事实或论文状态。\n"
            "4. final message 只用 1-2 句中文总结这次 agent 结果。\n"
        )
        return self._build_common_prompt(
            title=f"MD Agent {mode_label}",
            workspace=workspace,
            step_rule_text=self.step_rule_texts["md_advice_manager"],
            specific_instructions=instructions,
        )

    def load_pipeline_state(self, workspace: TailorWorkspace) -> dict[str, object]:
        return self._load_pipeline_state(workspace)

    def next_step_key(self, workspace: TailorWorkspace) -> str | None:
        pipeline_state = self._load_pipeline_state(workspace)
        for step in pipeline_state.get("steps", []):
            if step.get("status") != "succeeded":
                return str(step.get("key"))
        return None

    def current_step_key(self, workspace: TailorWorkspace) -> str | None:
        pipeline_state = self._load_pipeline_state(workspace)
        current = str(pipeline_state.get("current_step") or "")
        if current:
            return current
        return self.next_step_key(workspace)

    def current_step_log_text(self, workspace: TailorWorkspace) -> str:
        current_step_key = self.current_step_key(workspace)
        if not current_step_key:
            return ""
        return _read_text(workspace.step_logs[current_step_key])

    def mark_step_stopped(
        self,
        workspace: TailorWorkspace,
        *,
        step_key: str | None,
        message: str,
    ) -> dict[str, object]:
        pipeline_state = self._load_pipeline_state(workspace)
        target_step_key = step_key or str(pipeline_state.get("current_step") or "")
        if target_step_key in TAILOR_STEP_ORDER:
            step_record = self._get_step_record(pipeline_state, target_step_key)
            step_record["status"] = "stopped"
            step_record["error_text"] = ""
            step_record["message"] = message
            step_record["finished_at"] = datetime.now(timezone.utc).isoformat()
            pipeline_state["current_step"] = target_step_key
        elif target_step_key:
            pipeline_state["manual_stop_step"] = target_step_key
            pipeline_state["manual_stop_message"] = message
        pipeline_state["stopped"] = True
        self._save_pipeline_state(workspace, pipeline_state)
        return pipeline_state

    def run_pipeline_step(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        mode: str,
        step_key: str | None = None,
        session_id: str = "",
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> dict[str, object]:
        pipeline_state = self._load_pipeline_state(workspace)
        # 中文注释：在分发步骤之前先检测 projects.md / reference.md 是否更新过；如果更新过，
        # 自动把 matching 之后的步骤拍成 pending，避免拿陈旧 matching_analysis.json 继续跑。
        pipeline_state = self._check_asset_staleness(workspace, pipeline_state=pipeline_state, save=False)
        self._save_pipeline_state(workspace, pipeline_state)
        effective_session_id = session_id or str(pipeline_state.get("session_id") or "")
        step_keys: list[str]

        if mode == "restart":
            self._reset_pipeline_state(pipeline_state, workspace)
            effective_session_id = ""
            step_keys = list(TAILOR_STEP_ORDER)
            target_step_key = step_keys[0]
        elif mode == "step":
            target_step_key = step_key or self.current_step_key(workspace)
            if target_step_key is None:
                raise RuntimeError("当前没有可重跑的步骤")
            self._mark_steps_pending_from(
                pipeline_state,
                target_step_key,
                f"已请求重跑 {TAILOR_STEP_LABELS[target_step_key]}。",
            )
            step_keys = [target_step_key]
        else:
            target_step_key = self.next_step_key(workspace)
            if target_step_key is None:
                return {
                    "pipeline_state": pipeline_state,
                    "step_key": "",
                    "step_label": "",
                    "message": "所有步骤都已完成。",
                    "completed": True,
                    "stopped": False,
                    "session_id": effective_session_id,
                }
            step_keys = [target_step_key]

        if target_step_key not in TAILOR_STEP_ORDER:
            raise RuntimeError(f"未知步骤：{target_step_key}")

        if mode in {"restart", "step"}:
            pipeline_state["session_id"] = effective_session_id
            pipeline_state["stopped"] = False
            self._save_pipeline_state(workspace, pipeline_state)

        payload: dict[str, object] | None = None
        for current_step_key in step_keys:
            payload = self._run_single_pipeline_step(
                current_step_key,
                job,
                workspace,
                session_id=effective_session_id,
                pid_callback=pid_callback,
            )
            effective_session_id = str(payload.get("session_id") or "")
            if payload.get("stopped"):
                return payload

            current_state = payload.get("pipeline_state", {})
            if self._next_step_key_from_state(current_state) is None:
                return payload

        if payload is None:
            raise RuntimeError("没有可执行的流水线步骤")
        return payload

    def run_final_resume_prompt(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        instruction_text: str,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None = None,
    ) -> tuple[str, str]:
        return self.run_session_prompt(
            job,
            workspace,
            instruction_text=instruction_text,
            session_id=session_id,
            pid_callback=pid_callback,
        )

    def _run_single_pipeline_step(
        self,
        target_step_key: str,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None,
    ) -> dict[str, object]:
        pipeline_state = self._load_pipeline_state(workspace)
        previous_session_id = str(pipeline_state.get("session_id") or session_id or "")
        step_record = self._get_step_record(pipeline_state, target_step_key)
        step_record["status"] = "running"
        step_record["error_text"] = ""
        step_record["started_at"] = datetime.now(timezone.utc).isoformat()
        step_record["finished_at"] = None
        step_record["message"] = f"正在执行 {TAILOR_STEP_LABELS[target_step_key]}。"
        pipeline_state["current_step"] = target_step_key
        pipeline_state["session_id"] = session_id
        pipeline_state["stopped"] = False
        pipeline_state.pop("manual_stop_step", None)
        pipeline_state.pop("manual_stop_message", None)
        if target_step_key == "setup":
            pipeline_state["session_status"] = "establishing"
            pipeline_state["session_error"] = ""
            if not previous_session_id:
                pipeline_state["session_established_at"] = None
        self._save_pipeline_state(workspace, pipeline_state)
        if pid_callback is not None:
            pid_callback(target_step_key, None, session_id)

        try:
            message, next_session_id = self._execute_step(
                target_step_key,
                job,
                workspace,
                session_id=session_id,
                pid_callback=pid_callback,
            )
        except TailorStepStopped as exc:
            pipeline_state = self._load_pipeline_state(workspace)
            stopped_step = self._get_step_record(pipeline_state, target_step_key)
            if stopped_step.get("status") != "stopped":
                stopped_step["status"] = "stopped"
                stopped_step["message"] = str(exc)
                stopped_step["error_text"] = ""
                stopped_step["finished_at"] = datetime.now(timezone.utc).isoformat()
                pipeline_state["stopped"] = True
                self._save_pipeline_state(workspace, pipeline_state)
            return {
                "pipeline_state": pipeline_state,
                "step_key": target_step_key,
                "step_label": TAILOR_STEP_LABELS[target_step_key],
                "message": str(exc),
                "completed": False,
                "stopped": True,
                "session_id": session_id,
            }
        except Exception as exc:
            pipeline_state = self._load_pipeline_state(workspace)
            failed_step = self._get_step_record(pipeline_state, target_step_key)
            if failed_step.get("status") != "stopped":
                failed_step["status"] = "failed"
                failed_step["error_text"] = str(exc)
                failed_step["message"] = str(exc)
                failed_step["finished_at"] = datetime.now(timezone.utc).isoformat()
                pipeline_state["current_step"] = target_step_key
                pipeline_state["session_id"] = session_id
                if target_step_key == "setup":
                    pipeline_state["session_status"] = "failed"
                    pipeline_state["session_error"] = str(exc)
                self._save_pipeline_state(workspace, pipeline_state)
            raise

        pipeline_state = self._load_pipeline_state(workspace)
        step_record = self._get_step_record(pipeline_state, target_step_key)
        step_record["status"] = "succeeded"
        step_record["error_text"] = ""
        step_record["message"] = message
        step_record["finished_at"] = datetime.now(timezone.utc).isoformat()
        pipeline_state["session_id"] = next_session_id
        if next_session_id:
            pipeline_state["session_status"] = "ready"
            pipeline_state["session_error"] = ""
            if target_step_key == "setup" or not pipeline_state.get("session_established_at"):
                pipeline_state["session_established_at"] = datetime.now(timezone.utc).isoformat()
        if target_step_key == "matching":
            # 中文注释：matching 重新跑过后把 baseline 更新到当前 mtime，stale 提示也同步消除。
            pipeline_state["asset_baseline_mtime_ns"] = self._current_asset_mtime_ns()
            pipeline_state["assets_stale"] = False
            pipeline_state["assets_stale_message"] = ""
        next_step_key = self._next_step_key_from_state(pipeline_state)
        pipeline_state["current_step"] = next_step_key or ""
        self._save_pipeline_state(workspace, pipeline_state)
        return {
            "pipeline_state": pipeline_state,
            "step_key": target_step_key,
            "step_label": TAILOR_STEP_LABELS[target_step_key],
            "message": message,
            "completed": next_step_key is None,
            "stopped": False,
            "session_id": next_session_id,
        }

    def _copy_resume_source(self, relative_path: str, target_path: Path) -> None:
        source_path = _resume_source_path(relative_path)
        if not source_path.exists():
            raise FileNotFoundError(f"base resume not found: {relative_path}")
        shutil.copyfile(source_path, target_path)

    def _resolve_workspace_dir_for_job(self, workspace_root: Path, job: JobRecord) -> Path:
        for child in sorted(workspace_root.iterdir()):
            if not child.is_dir():
                continue
            snapshot_payload = _safe_json_load(child / "job_snapshot.json")
            if not snapshot_payload:
                continue
            if snapshot_payload.get("unique_key") == job.unique_key:
                return child.resolve()
            if job.job_url and snapshot_payload.get("job_url") == job.job_url:
                return child.resolve()

        date_stamp = datetime.now(LOCAL_TIMEZONE).strftime("%Y%m%d")
        base_name = f"{date_stamp}_{_role_segment(job.company)}_{_role_segment(job.title)}"
        candidate = workspace_root / base_name
        suffix = 2
        while candidate.exists():
            snapshot_payload = _safe_json_load(candidate / "job_snapshot.json")
            if snapshot_payload.get("unique_key") == job.unique_key:
                return candidate.resolve()
            candidate = workspace_root / f"{base_name}_{suffix}"
            suffix += 1
        return candidate.resolve()

    def _final_resume_filename(self, job: JobRecord, workspace_dir: Path) -> str:
        date_stamp = (
            workspace_dir.name[:8]
            if len(workspace_dir.name) >= 8
            else datetime.now(LOCAL_TIMEZONE).strftime("%Y%m%d")
        )
        return f"cv-{_role_segment(job.company)}-{date_stamp[2:]}.tex"

    def _default_pipeline_state(
        self,
        *,
        workspace_dir: Path,
        selected_resume_path: str,
        final_resume_name: str,
    ) -> dict[str, object]:
        steps = []
        for step_key in TAILOR_STEP_ORDER:
            steps.append(
                {
                    "key": step_key,
                    "label": TAILOR_STEP_LABELS[step_key],
                    "status": "pending",
                    "message": "",
                    "error_text": "",
                    "started_at": None,
                    "finished_at": None,
                    "log_path": str(workspace_dir / f"{step_key}.log"),
                    "prompt_path": str(workspace_dir / f"{step_key}.prompt.md"),
                    "last_message_path": str(workspace_dir / f"{step_key}_last_message.md"),
                }
            )
        return {
            "version": 5,
            "workflow_mode": "session_workbench",
            "advice_status": "idle",
            "advice_updated_at": None,
            "advice_error": "",
            "advice_message": "",
            "revision_advice_status": "idle",
            "revision_advice_updated_at": None,
            "revision_advice_error": "",
            "revision_advice_message": "",
            "md_agent_status": "idle",
            "md_agent_target": "",
            "md_agent_mode": "",
            "md_agent_updated_at": None,
            "md_agent_error": "",
            "md_agent_message": "",
            "session_id": "",
            "session_status": "not_started",
            "session_established_at": None,
            "session_error": "",
            "current_step": "setup",
            "selected_resume_path": selected_resume_path,
            "stopped": False,
            "manual_stop_step": "",
            "manual_stop_message": "",
            "asset_baseline_mtime_ns": 0,
            "assets_stale": False,
            "assets_stale_message": "",
            "artifacts": {
                "role": TAILOR_ARTIFACT_KEYS["role"],
                "notes": TAILOR_ARTIFACT_KEYS["notes"],
                "snapshot": TAILOR_ARTIFACT_KEYS["snapshot"],
                "template": TAILOR_ARTIFACT_KEYS["template"],
                "advice": TAILOR_ARTIFACT_KEYS["advice"],
                "revision_advice": TAILOR_ARTIFACT_KEYS["revision_advice"],
                "matching_analysis": TAILOR_ARTIFACT_KEYS["matching_analysis"],
                "tailored_resume": TAILOR_ARTIFACT_KEYS["tailored_resume"],
                "fact_check_report": TAILOR_ARTIFACT_KEYS["fact_check_report"],
                "final_resume": final_resume_name,
                "final_pdf": Path(final_resume_name).with_suffix(".pdf").name,
                "diff_tex": TAILOR_ARTIFACT_KEYS["diff_tex"],
                "diff_pdf": TAILOR_ARTIFACT_KEYS["diff_pdf"],
                "vibe_review": TAILOR_ARTIFACT_KEYS["vibe_review"],
            },
            "steps": steps,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _normalize_pipeline_state(
        self,
        state: dict[str, object],
        *,
        workspace_dir: Path,
        selected_resume_path: str,
        final_resume_name: str,
    ) -> dict[str, object]:
        default_state = self._default_pipeline_state(
            workspace_dir=workspace_dir,
            selected_resume_path=selected_resume_path,
            final_resume_name=final_resume_name,
        )
        if not state:
            return default_state

        raw_steps = [
            step
            for step in state.get("steps", [])
            if isinstance(step, dict) and step.get("key")
        ]
        steps_by_key = {str(step.get("key")): step for step in raw_steps}

        normalized_steps = []
        for default_step in default_state["steps"]:
            step_key = str(default_step["key"])
            saved_step = steps_by_key.get(step_key) or self._legacy_step_record(
                step_key,
                legacy_steps=steps_by_key,
            )
            normalized_steps.append(
                {
                    "key": step_key,
                    "label": saved_step.get("label", default_step["label"]) if saved_step else default_step["label"],
                    "status": saved_step.get("status", default_step["status"]) if saved_step else default_step["status"],
                    "message": saved_step.get("message", default_step["message"]) if saved_step else default_step["message"],
                    "error_text": saved_step.get("error_text", default_step["error_text"]) if saved_step else default_step["error_text"],
                    "started_at": saved_step.get("started_at") if saved_step else None,
                    "finished_at": saved_step.get("finished_at") if saved_step else None,
                    "log_path": saved_step.get("log_path", default_step["log_path"]) if saved_step else default_step["log_path"],
                    "prompt_path": saved_step.get("prompt_path", default_step["prompt_path"]) if saved_step else default_step["prompt_path"],
                    "last_message_path": saved_step.get("last_message_path", default_step["last_message_path"]) if saved_step else default_step["last_message_path"],
                }
            )

        current_step = str(state.get("current_step") or default_state["current_step"])
        current_step = LEGACY_STEP_KEY_MAP.get(current_step, current_step)
        if current_step not in TAILOR_STEP_ORDER:
            current_step = default_state["current_step"]

        artifacts = {
            **default_state["artifacts"],
            **(state.get("artifacts", {}) or {}),
        }
        if "diff" in artifacts and "diff_tex" not in artifacts:
            artifacts["diff_tex"] = artifacts["diff"]

        session_status = str(
            state.get("session_status")
            or ("ready" if state.get("session_id") else "not_started")
        )
        if session_status not in {"not_started", "establishing", "ready", "failed"}:
            session_status = "ready" if state.get("session_id") else "not_started"

        return {
            "version": 5,
            "workflow_mode": "session_workbench",
            "advice_status": str(state.get("advice_status") or default_state["advice_status"]),
            "advice_updated_at": state.get("advice_updated_at"),
            "advice_error": str(state.get("advice_error") or ""),
            "advice_message": str(state.get("advice_message") or ""),
            "revision_advice_status": str(
                state.get("revision_advice_status")
                or default_state["revision_advice_status"]
            ),
            "revision_advice_updated_at": state.get("revision_advice_updated_at"),
            "revision_advice_error": str(state.get("revision_advice_error") or ""),
            "revision_advice_message": str(
                state.get("revision_advice_message") or ""
            ),
            "md_agent_status": str(state.get("md_agent_status") or default_state["md_agent_status"]),
            "md_agent_target": str(state.get("md_agent_target") or ""),
            "md_agent_mode": str(state.get("md_agent_mode") or ""),
            "md_agent_updated_at": state.get("md_agent_updated_at"),
            "md_agent_error": str(state.get("md_agent_error") or ""),
            "md_agent_message": str(state.get("md_agent_message") or ""),
            "session_id": str(state.get("session_id") or ""),
            "session_status": session_status,
            "session_established_at": state.get("session_established_at"),
            "session_error": str(state.get("session_error") or ""),
            "current_step": current_step,
            "selected_resume_path": str(
                state.get("selected_resume_path") or selected_resume_path
            ),
            "stopped": bool(state.get("stopped", False)),
            "manual_stop_step": str(state.get("manual_stop_step") or ""),
            "manual_stop_message": str(state.get("manual_stop_message") or ""),
            "artifacts": artifacts,
            "steps": normalized_steps,
            "tailor_loop_soft_pass": (
                state.get("tailor_loop_soft_pass")
                if isinstance(state.get("tailor_loop_soft_pass"), dict)
                else None
            ),
            "asset_baseline_mtime_ns": int(state.get("asset_baseline_mtime_ns") or 0),
            "assets_stale": bool(state.get("assets_stale", False)),
            "assets_stale_message": str(state.get("assets_stale_message") or ""),
            "updated_at": str(state.get("updated_at") or default_state["updated_at"]),
        }

    def _legacy_step_record(
        self,
        step_key: str,
        *,
        legacy_steps: dict[str, dict[str, object]],
    ) -> dict[str, object] | None:
        if step_key == "tailor_loop":
            tailor_step = legacy_steps.get("tailor")
            fact_step = legacy_steps.get("fact_check")
            if fact_step:
                merged = dict(fact_step)
                merged["label"] = TAILOR_STEP_LABELS["tailor_loop"]
                merged["started_at"] = fact_step.get("started_at") or (
                    tailor_step.get("started_at") if tailor_step else None
                )
                return merged
            if tailor_step:
                merged = dict(tailor_step)
                merged["label"] = TAILOR_STEP_LABELS["tailor_loop"]
                return merged
            return None
        if step_key == "final_proof":
            finalize_step = legacy_steps.get("finalize")
            if finalize_step:
                merged = dict(finalize_step)
                merged["label"] = TAILOR_STEP_LABELS["final_proof"]
                return merged
        return None

    def _load_pipeline_state(self, workspace: TailorWorkspace) -> dict[str, object]:
        return self._normalize_pipeline_state(
            _safe_json_load(workspace.pipeline_state_path),
            workspace_dir=workspace.workspace_dir,
            selected_resume_path=workspace.base_resume_path,
            final_resume_name=workspace.final_resume_path.name,
        )

    def _save_pipeline_state(self, workspace: TailorWorkspace, pipeline_state: dict[str, object]) -> None:
        pipeline_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        workspace.pipeline_state_path.write_text(
            json.dumps(pipeline_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _get_step_record(self, pipeline_state: dict[str, object], step_key: str) -> dict[str, object]:
        for step in pipeline_state.get("steps", []):
            if step.get("key") == step_key:
                return step
        raise KeyError(f"step not found: {step_key}")

    def _reset_pipeline_state(self, pipeline_state: dict[str, object], workspace: TailorWorkspace) -> None:
        reset_state = self._default_pipeline_state(
            workspace_dir=workspace.workspace_dir,
            selected_resume_path=workspace.base_resume_path,
            final_resume_name=workspace.final_resume_path.name,
        )
        pipeline_state.clear()
        pipeline_state.update(reset_state)

    def _mark_steps_pending_from(
        self,
        pipeline_state: dict[str, object],
        start_step_key: str,
        message: str,
    ) -> None:
        reached = False
        for step in pipeline_state.get("steps", []):
            if step.get("key") == start_step_key:
                reached = True
            if not reached:
                continue
            step["status"] = "pending"
            step["error_text"] = ""
            step["started_at"] = None
            step["finished_at"] = None
            step["message"] = message if step.get("key") == start_step_key else ""
        pipeline_state["current_step"] = start_step_key
        pipeline_state["stopped"] = False

    def _next_step_key_from_state(self, pipeline_state: dict[str, object]) -> str | None:
        for step in pipeline_state.get("steps", []):
            if step.get("status") != "succeeded":
                return str(step.get("key"))
        return None

    def _execute_step(
        self,
        step_key: str,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None,
    ) -> tuple[str, str]:
        if step_key == "setup":
            return self._run_setup_step(
                job,
                workspace,
                session_id=session_id,
                pid_callback=pid_callback,
            )
        if step_key == "matching":
            return self._run_codex_step(
                step_key="matching",
                workspace=workspace,
                prompt=self._build_matching_prompt(job, workspace),
                expected_paths=[workspace.matching_analysis_path],
                session_id=session_id,
                pid_callback=pid_callback,
            )
        if step_key == "tailor_loop":
            return self._run_tailor_loop(
                job=job,
                workspace=workspace,
                session_id=session_id,
                pid_callback=pid_callback,
            )
        if step_key == "final_proof":
            message, next_session_id = self._run_codex_step(
                step_key="final_proof",
                workspace=workspace,
                prompt=self._build_final_proof_prompt(job, workspace),
                expected_paths=[workspace.final_resume_path],
                session_id=session_id,
                pid_callback=pid_callback,
            )
            self._compile_pdf(workspace.final_resume_path)
            self._ensure_diff_pdf(workspace)
            return (
                f"{message} 已生成 {workspace.final_resume_pdf_path.name} 与 {workspace.diff_pdf_path.name}。",
                next_session_id,
            )
        if step_key == "vibe_review":
            message, next_session_id = self._run_codex_step(
                step_key="vibe_review",
                workspace=workspace,
                prompt=self._build_vibe_review_prompt(job, workspace),
                expected_paths=[workspace.final_resume_path, workspace.vibe_review_path],
                session_id=session_id,
                pid_callback=pid_callback,
            )
            self._compile_pdf(workspace.final_resume_path)
            self._ensure_diff_pdf(workspace)
            return (
                f"{message} 已更新最终 PDF 与 diff PDF。",
                next_session_id,
            )
        raise RuntimeError(f"unsupported step: {step_key}")

    def _run_setup_step(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None,
    ) -> tuple[str, str]:
        log_lines = [
            f"workspace: {workspace.workspace_dir}",
            f"role: {workspace.role_path.name}",
            f"notes: {workspace.notes_path.name}",
            f"template: {workspace.base_resume_copy_path.name}",
            f"selected_resume: {workspace.base_resume_path}",
            f"job: {job.title} @ {job.company}",
        ]
        workspace.step_logs["setup"].write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        bootstrap_message, next_session_id = self._run_codex_step(
            step_key="setup",
            workspace=workspace,
            prompt=self._build_setup_prompt(job, workspace),
            expected_paths=[],
            session_id=session_id,
            pid_callback=pid_callback,
            log_title="setup bootstrap",
            append_log=True,
            prompt_title="setup bootstrap",
        )
        if not next_session_id.strip():
            raise RuntimeError("Setup 已执行，但没有拿到 Codex session id。")
        final_message = "Role 工作区与模板文件已准备好，当前 Codex session 已建立。"
        if bootstrap_message:
            final_message = f"{final_message} {bootstrap_message}"
        workspace.step_message_files["setup"].write_text(
            final_message.strip(),
            encoding="utf-8",
        )
        return final_message.strip(), next_session_id

    def _current_asset_mtime_ns(self) -> int:
        latest = 0
        for path in (PROJECT_LIBRARY_PATH, REFERENCE_LIBRARY_PATH):
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            if mtime_ns > latest:
                latest = mtime_ns
        return latest

    def _refresh_asset_baseline(self, workspace: TailorWorkspace) -> None:
        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["asset_baseline_mtime_ns"] = self._current_asset_mtime_ns()
        pipeline_state["assets_stale"] = False
        pipeline_state["assets_stale_message"] = ""
        self._save_pipeline_state(workspace, pipeline_state)

    def _check_asset_staleness(
        self,
        workspace: TailorWorkspace,
        *,
        pipeline_state: dict[str, object] | None = None,
        save: bool = True,
    ) -> dict[str, object]:
        state = pipeline_state if pipeline_state is not None else self._load_pipeline_state(workspace)
        baseline_raw = state.get("asset_baseline_mtime_ns") or 0
        try:
            baseline = int(baseline_raw)
        except (TypeError, ValueError):
            baseline = 0
        current = self._current_asset_mtime_ns()
        is_stale = bool(baseline) and current > baseline

        if is_stale:
            stale_message = "projects.md / reference.md 已更新，建议重新跑 matching 与 tailor_loop。"
            already_marked = bool(state.get("assets_stale"))
            state["assets_stale"] = True
            state["assets_stale_message"] = stale_message
            if not already_marked:
                # 中文注释：第一次发现 stale 时把 matching 之后的步骤拍成 pending，提示用户重跑。
                self._mark_steps_pending_from(state, "matching", stale_message)
        else:
            state["assets_stale"] = False
            state["assets_stale_message"] = ""
            if not baseline:
                state["asset_baseline_mtime_ns"] = current

        if save and pipeline_state is None:
            self._save_pipeline_state(workspace, state)
        return state

    def _normalize_soft_pass_issue(self, issue: object) -> dict[str, str]:
        if not isinstance(issue, dict):
            return {}
        return {
            "content": str(issue.get("content") or "").strip(),
            "issue": str(issue.get("issue") or "").strip(),
            "recommendation": str(issue.get("recommendation") or "").strip(),
            "source_truth": str(issue.get("source_truth") or "").strip(),
        }

    def _soft_pass_todos_path(self, workspace: TailorWorkspace) -> Path:
        return workspace.workspace_dir / "soft_pass_todos.md"

    def _clear_soft_pass_state(self, workspace: TailorWorkspace) -> None:
        pipeline_state = self._load_pipeline_state(workspace)
        if "tailor_loop_soft_pass" in pipeline_state:
            pipeline_state["tailor_loop_soft_pass"] = None
            self._save_pipeline_state(workspace, pipeline_state)
        todo_path = self._soft_pass_todos_path(workspace)
        if todo_path.exists():
            todo_path.unlink()

    def _record_soft_pass_state(
        self,
        workspace: TailorWorkspace,
        *,
        attempt: int,
        issues: list[object],
        summary: str,
    ) -> None:
        normalized = [self._normalize_soft_pass_issue(item) for item in issues]
        normalized = [entry for entry in normalized if entry]
        recorded_at = datetime.now(timezone.utc).isoformat()
        pipeline_state = self._load_pipeline_state(workspace)
        pipeline_state["tailor_loop_soft_pass"] = {
            "attempt": attempt,
            "issue_count": len(normalized),
            "issues": normalized,
            "summary": summary,
            "recorded_at": recorded_at,
        }
        self._save_pipeline_state(workspace, pipeline_state)

        lines = [
            "# Soft-pass TODOs",
            "",
            f"- 第 {attempt} 轮 fact-check 仍剩 {len(normalized)} 个 minor 问题，已 soft-pass 继续流水线。",
            "- 请在 final tex 对应章节首行插入 `% TODO: <issue> -> <recommendation>` 注释，便于人工复核。",
            "",
        ]
        for index, entry in enumerate(normalized, start=1):
            issue_text = entry.get("issue") or "未说明"
            recommendation = entry.get("recommendation") or "请回到 projects.md / reference.md 对齐"
            content_text = entry.get("content") or "未提供"
            source_truth = entry.get("source_truth") or "请自行核对源文件"
            lines.extend(
                [
                    f"## {index}. {issue_text}",
                    f"- 涉及内容: {content_text}",
                    f"- 修复建议: {recommendation}",
                    f"- 来源事实: {source_truth}",
                    "",
                ]
            )
        self._soft_pass_todos_path(workspace).write_text(
            "\n".join(lines).rstrip() + "\n",
            encoding="utf-8",
        )

    def _run_tailor_loop(
        self,
        *,
        job: JobRecord,
        workspace: TailorWorkspace,
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None,
    ) -> tuple[str, str]:
        current_session_id = session_id
        issues_summary = ""
        loop_messages: list[str] = []
        workspace.step_logs["tailor_loop"].write_text("", encoding="utf-8")
        # 中文注释：进入 tailor loop 前先清空上一轮残留的 soft-pass 状态，避免新 run 沿用旧 TODO。
        self._clear_soft_pass_state(workspace)

        for attempt in range(1, MAX_TAILOR_LOOP_ATTEMPTS + 1):
            tailor_message, current_session_id = self._run_codex_step(
                step_key="tailor_loop",
                workspace=workspace,
                prompt=self._build_content_tailor_prompt(
                    job,
                    workspace,
                    attempt=attempt,
                    issues_summary=issues_summary,
                ),
                expected_paths=[workspace.tailored_resume_path],
                session_id=current_session_id,
                pid_callback=pid_callback,
                log_title=f"content-tailor round {attempt}",
                append_log=True,
                prompt_title=f"content-tailor round {attempt}",
            )
            loop_messages.append(f"第 {attempt} 轮 content-tailor: {tailor_message}")

            fact_message, current_session_id = self._run_codex_step(
                step_key="tailor_loop",
                workspace=workspace,
                prompt=self._build_fact_check_prompt(job, workspace, attempt=attempt),
                expected_paths=[workspace.fact_check_report_path],
                session_id=current_session_id,
                pid_callback=pid_callback,
                log_title=f"fact-check round {attempt}",
                append_log=True,
                prompt_title=f"fact-check round {attempt}",
            )
            report = _safe_json_load(workspace.fact_check_report_path)
            passed = bool(report.get("passed"))
            issues = report.get("issues", []) if isinstance(report, dict) else []
            issue_count = len(issues) if isinstance(issues, list) else int(report.get("issues_found") or 0)
            loop_messages.append(f"第 {attempt} 轮 fact-check: {fact_message}")

            if passed:
                final_message = f"Tailor Loop 在第 {attempt} 轮通过事实核查。"
                workspace.step_message_files["tailor_loop"].write_text(
                    "\n".join(loop_messages + [final_message]) + "\n",
                    encoding="utf-8",
                )
                return final_message, current_session_id

            issues_summary = self._format_fact_check_feedback(report)
            loop_messages.append(f"第 {attempt} 轮未通过，共 {issue_count} 个问题。")

        # soft-pass: 如果最后一轮的问题数 <= 2，视为 passed_with_warnings 继续流水线
        if issue_count <= 2:
            soft_pass_message = (
                f"Tailor Loop 在第 {MAX_TAILOR_LOOP_ATTEMPTS} 轮 soft-pass："
                f"剩余 {issue_count} 个 minor 问题，已继续流水线。请人工复核。"
            )
            self._record_soft_pass_state(
                workspace,
                attempt=MAX_TAILOR_LOOP_ATTEMPTS,
                issues=issues if isinstance(issues, list) else [],
                summary=soft_pass_message,
            )
            workspace.step_message_files["tailor_loop"].write_text(
                "\n".join(loop_messages + [soft_pass_message]) + "\n",
                encoding="utf-8",
            )
            return soft_pass_message, current_session_id

        failure_message = "Tailor Loop 在 3 轮后仍未通过事实核查，请人工介入。"
        workspace.step_message_files["tailor_loop"].write_text(
            "\n".join(loop_messages + [failure_message]) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError(failure_message)

    def _run_codex_step(
        self,
        *,
        step_key: str,
        workspace: TailorWorkspace,
        prompt: str,
        expected_paths: list[Path],
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None,
        log_title: str | None = None,
        append_log: bool = False,
        prompt_title: str | None = None,
    ) -> tuple[str, str]:
        self._write_prompt_file(
            workspace.step_prompt_files[step_key],
            prompt=prompt,
            title=prompt_title or log_title or step_key,
            append=append_log,
        )

        command = self._build_codex_command(
            session_id=session_id,
            output_path=workspace.step_message_files[step_key],
        )
        started_at = datetime.now(timezone.utc)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PARENT_ROOT),
        )
        if pid_callback is not None:
            pid_callback(step_key, process.pid, session_id)

        try:
            stdout, stderr = process.communicate(
                prompt,
                timeout=self.settings.app.codex_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            self._append_step_log(
                workspace.step_logs[step_key],
                title=log_title or step_key,
                stdout=stdout,
                stderr=f"{stderr}\nTIMEOUT: {exc}",
                append=append_log,
            )
            raise RuntimeError(f"{TAILOR_STEP_LABELS[step_key]} 执行超时") from exc
        finally:
            if pid_callback is not None:
                pid_callback(step_key, None, session_id)

        next_session_id = (
            session_id
            or self._extract_session_id_from_codex_json(stdout)
            or self._infer_session_id_since(started_at)
        )
        if pid_callback is not None:
            pid_callback(step_key, None, next_session_id)

        self._append_step_log(
            workspace.step_logs[step_key],
            title=log_title or step_key,
            stdout=stdout,
            stderr=stderr,
            append=append_log,
        )

        if process.returncode != 0:
            if self._step_was_stopped(workspace, step_key):
                raise TailorStepStopped("已手动停止当前精修步骤。")
            raise RuntimeError(stderr.strip() or f"{step_key} step failed")

        missing_outputs = [path.name for path in expected_paths if not path.exists()]
        if missing_outputs:
            raise RuntimeError(f"{step_key} 未生成预期文件: {', '.join(missing_outputs)}")

        message = _read_text(workspace.step_message_files[step_key]).strip()
        return message or f"{TAILOR_STEP_LABELS[step_key]} 已完成。", next_session_id

    def _run_workspace_action(
        self,
        *,
        action_key: str,
        title: str,
        workspace: TailorWorkspace,
        prompt: str,
        expected_paths: list[Path],
        session_id: str,
        pid_callback: Callable[[str, int | None, str], None] | None,
    ) -> tuple[str, str]:
        prompt_path = workspace.action_prompt_files[action_key]
        message_path = workspace.action_message_files[action_key]
        log_path = workspace.action_logs[action_key]
        self._write_prompt_file(
            prompt_path,
            prompt=prompt,
            title=title,
            append=False,
        )

        command = self._build_codex_command(
            session_id=session_id,
            output_path=message_path,
        )
        started_at = datetime.now(timezone.utc)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PARENT_ROOT),
        )
        if pid_callback is not None:
            pid_callback(action_key, process.pid, session_id)

        try:
            stdout, stderr = process.communicate(
                prompt,
                timeout=self.settings.app.codex_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            self._append_step_log(
                log_path,
                title=title,
                stdout=stdout,
                stderr=f"{stderr}\nTIMEOUT: {exc}",
                append=False,
            )
            raise RuntimeError(f"{title} 执行超时") from exc
        finally:
            if pid_callback is not None:
                pid_callback(action_key, None, session_id)

        next_session_id = (
            session_id
            or self._extract_session_id_from_codex_json(stdout)
            or self._infer_session_id_since(started_at)
        )
        if pid_callback is not None:
            pid_callback(action_key, None, next_session_id)

        self._append_step_log(
            log_path,
            title=title,
            stdout=stdout,
            stderr=stderr,
            append=False,
        )

        if process.returncode != 0:
            if self._step_was_stopped(workspace, action_key):
                raise TailorStepStopped("已手动停止当前精修步骤。")
            raise RuntimeError(stderr.strip() or f"{title} failed")

        missing_outputs = [path.name for path in expected_paths if not path.exists()]
        if missing_outputs:
            raise RuntimeError(f"{title} 未生成预期文件: {', '.join(missing_outputs)}")

        message = _read_text(message_path).strip()
        return message or f"{title} 已完成。", next_session_id

    def _build_codex_command(self, *, session_id: str, output_path: Path) -> list[str]:
        if session_id:
            return [
                "codex",
                "-C",
                str(PARENT_ROOT),
                "exec",
                "resume",
                "--json",
                "--skip-git-repo-check",
                "--full-auto",
                "-o",
                str(output_path),
                session_id,
                "-",
            ]
        return [
            "codex",
            "-C",
            str(PARENT_ROOT),
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--full-auto",
            "-o",
            str(output_path),
            "-",
        ]

    def _extract_session_id_from_codex_json(self, stdout_text: str) -> str:
        for raw_line in stdout_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "session_meta":
                continue
            session_id = str((payload.get("payload") or {}).get("id") or "").strip()
            if session_id:
                return session_id
        return ""

    def _infer_session_id_since(self, started_at: datetime) -> str:
        session_root = Path.home() / ".codex" / "sessions"
        if not session_root.exists():
            return ""

        latest_candidate: tuple[datetime, Path] | None = None
        cutoff = started_at - timedelta(seconds=3)
        for path in session_root.rglob("rollout-*.jsonl"):
            try:
                modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if modified_at < cutoff:
                continue
            if latest_candidate is None or modified_at > latest_candidate[0]:
                latest_candidate = (modified_at, path)

        if latest_candidate is None:
            return ""
        matched = SESSION_FILE_PATTERN.search(latest_candidate[1].name)
        return matched.group(1) if matched else ""

    def _step_was_stopped(self, workspace: TailorWorkspace, step_key: str) -> bool:
        pipeline_state = self._load_pipeline_state(workspace)
        if step_key in TAILOR_STEP_ORDER:
            return self._get_step_record(pipeline_state, step_key).get("status") == "stopped"
        return str(pipeline_state.get("manual_stop_step") or "") == step_key

    def _append_step_log(
        self,
        path: Path,
        *,
        title: str,
        stdout: str,
        stderr: str,
        append: bool,
    ) -> None:
        section = "\n".join(
            [
                f"## {title}",
                "",
                "### STDOUT",
                stdout.rstrip(),
                "",
                "### STDERR",
                stderr.rstrip(),
                "",
            ]
        )
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(section.strip() + "\n")

    def _write_prompt_file(
        self,
        path: Path,
        *,
        prompt: str,
        title: str,
        append: bool,
    ) -> None:
        content = f"## {title}\n\n{prompt.rstrip()}\n"
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(content + ("\n" if append else ""))

    def _format_fact_check_feedback(self, report: dict[str, object]) -> str:
        issues = report.get("issues", [])
        if not isinstance(issues, list) or not issues:
            issues_found = int(report.get("issues_found") or 0)
            if issues_found <= 0:
                return "上一轮 fact check 没有给出结构化问题，但结果未通过，请谨慎压缩和修正文案。"
            return f"上一轮 fact check 未通过，共 {issues_found} 个问题。"

        lines = ["上一轮 fact-check 未通过，请逐条修复以下问题："]
        for index, issue in enumerate(issues[:12], start=1):
            if not isinstance(issue, dict):
                continue
            content = str(issue.get("content") or "").strip()
            detail = str(issue.get("issue") or "").strip()
            recommendation = str(issue.get("recommendation") or "").strip()
            source_truth = str(issue.get("source_truth") or "").strip()
            lines.append(
                f"{index}. 问题: {detail or '未说明'} | 内容: {content or '未提供'} |"
                f" 建议: {recommendation or '请回到 projects.md 对齐'} |"
                f" 来源事实: {source_truth or '请自行核对源文件'}"
            )
        return "\n".join(lines)

    def _compile_pdf(self, tex_path: Path) -> Path:
        if not tex_path.exists():
            raise FileNotFoundError(f"tex not found: {tex_path.name}")
        result = subprocess.run(
            [
                "latexmk",
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                tex_path.name,
            ],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            timeout=self.settings.app.codex_timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"latexmk failed: {tex_path.name}")
        pdf_path = tex_path.with_suffix(".pdf")
        if not pdf_path.exists():
            raise RuntimeError(f"未生成 PDF: {pdf_path.name}")
        return pdf_path

    def _ensure_diff_pdf(self, workspace: TailorWorkspace) -> Path:
        if not workspace.final_resume_path.exists():
            raise FileNotFoundError(f"final tex not found: {workspace.final_resume_path.name}")

        result = subprocess.run(
            [
                "latexdiff",
                workspace.base_resume_copy_path.name,
                workspace.final_resume_path.name,
            ],
            cwd=workspace.workspace_dir,
            capture_output=True,
            text=True,
            timeout=self.settings.app.codex_timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "latexdiff failed")
        workspace.diff_path.write_text(result.stdout, encoding="utf-8")
        return self._compile_pdf(workspace.diff_path)

    def _build_common_prompt(
        self,
        *,
        title: str,
        workspace: TailorWorkspace,
        step_rule_text: str = "",
        specific_instructions: str,
    ) -> str:
        step_rule_block = (
            f"<step_rule>\n{step_rule_text}\n</step_rule>\n\n"
            if step_rule_text.strip()
            else ""
        )
        return (
            f"你正在执行 resume tailor pipeline 的 {title}。\n"
            f"唯一允许修改的目录: {workspace.workspace_dir}\n"
            f"工作区相对路径: {_safe_relative_path(workspace.workspace_dir, PARENT_ROOT)}\n"
            "不允许修改 .codex、.claude、asset、General、config 或其他工作区。\n"
            "这一步使用内置 step 规则，不读取 .claude/agents。\n"
            "当前流水线固定为：setup -> matching -> tailor_loop -> final_proof -> vibe_review。\n"
            "tailor_loop 内部固定为 content-tailor / fact-check 循环，最多 3 轮。\n"
            "role.md 是当前岗位信息的主文档；静态岗位快照只做留档，不作为主输入。\n"
            "所有事实只能来自 role.md、user_notes.md、基础简历、projects.md、reference.md。\n"
            "除当前步骤明确允许的输出文件外，不要改其他文件。\n"
            "final message 用 1-2 句简体中文总结。\n\n"
            f"{step_rule_block}"
            f"{specific_instructions}\n"
        )

    def _build_skill_prompt(
        self,
        *,
        title: str,
        workspace: TailorWorkspace,
        task_skill_key: str,
        specific_instructions: str,
        allowed_write_paths: list[Path] | None = None,
    ) -> str:
        task_skill_text = self.skill_texts.get(task_skill_key, "").strip()
        shared_block = (
            f"<shared_skill>\n{EMBEDDED_SHARED_SKILL_TEXT}\n</shared_skill>\n\n"
            if EMBEDDED_SHARED_SKILL_TEXT
            else ""
        )
        task_block = (
            f"<task_skill>\n{task_skill_text}\n</task_skill>\n\n"
            if task_skill_text
            else ""
        )
        write_block = ""
        if allowed_write_paths:
            write_block = "本步骤允许写入的文件:\n" + "\n".join(
                f"- {path}" for path in allowed_write_paths
            ) + "\n\n"
        return (
            f"你正在执行 resume tailor workbench 的 {title}。\n"
            "这套工作台不依赖外部自动发现 skill；以下内联文本就是当前唯一有效规则。\n"
            "当前不读取 .claude/agents；只使用内联 skill 和内置 step 规则。\n"
            f"唯一允许修改的目录: {workspace.workspace_dir}\n"
            f"工作区相对路径: {_safe_relative_path(workspace.workspace_dir, PARENT_ROOT)}\n"
            "不允许修改 .codex、.claude、asset、General、config 或其他工作区。\n"
            "role.md 是当前岗位信息的主文档；job_snapshot.json 只做留档，不是主输入。\n"
            "所有事实只能来自 role.md、user_notes.md、基础简历、projects.md、reference.md。\n"
            "final message 用 1-2 句简体中文总结。\n\n"
            f"{shared_block}"
            f"{task_block}"
            f"{write_block}"
            f"{specific_instructions}\n"
        )

    def _build_advice_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        template_lines = "\n".join(
            f"- {resume_path}"
            for resume_path in self.available_resume_files()
        )
        instructions = (
            "本步骤目标：生成一份给用户看的流程建议，不要直接改简历。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {PROJECT_LIBRARY_PATH}\n"
            f"- 当前模板副本: {workspace.base_resume_copy_path}\n\n"
            f"可选基础模板:\n{template_lines}\n\n"
            f"输出文件:\n- {workspace.advice_path}\n\n"
            "输出要求:\n"
            "1. 用 Markdown，结构固定为：岗位判断 / 项目组合建议 / 模板建议 / 第一轮 vibe 提示 / 风险提醒。\n"
            "2. 项目组合建议必须明确写出 2-4 个最值得保留或组合的项目故事线。\n"
            "3. 模板建议必须点名一个最推荐模板，并说明为什么它比当前模板更合适。\n"
            "4. 第一轮 vibe 提示请直接写成可以复制给 Codex session 的中文指令。\n"
            "5. 不要虚构任何项目、成果或文献。\n"
            "6. final message 只用 1-2 句中文总结推荐策略。\n"
        )
        return self._build_common_prompt(
            title="Advice",
            workspace=workspace,
            step_rule_text=self.step_rule_texts["matching"],
            specific_instructions=instructions,
        )

    def _build_revision_advice_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        revision_source_path, _, uses_final_resume = self.revision_resume_source(workspace)
        revision_signal_block = self._build_revision_signal_block(workspace)
        revision_source_label = (
            "当前最新简历 final tex"
            if uses_final_resume
            else "当前模板副本（尚未生成 final tex，已自动回退）"
        )
        instructions = (
            "本步骤目标：基于岗位和当前简历版本，生成一份简洁、可执行的改稿建议，不直接改 tex。\n"
            "这是当前已建立 Codex session 的后续回合；不要重新做 setup，也不要重复总结整个工作区。\n"
            "默认沿用当前 session 已记住的上下文，只在需要核对事实时回看文件。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {PROJECT_LIBRARY_PATH}\n- {REFERENCE_LIBRARY_PATH}\n"
            f"- {revision_source_label}: {revision_source_path}\n\n"
            f"{revision_signal_block}\n\n"
            f"输出文件:\n- {workspace.revision_advice_path}\n\n"
            "思考步骤（不输出到文件中，仅用于内部推理）：\n"
            "a. 先快速列出岗位的 3 个核心诉求（不是关键词，是能力维度）。\n"
            "b. 对照当前简历，判断哪些 bullet 已经覆盖、哪些缺失、哪些弱相关。\n"
            "c. 基于判断再输出正式的修改建议和 Session 指令。\n\n"
            "输出要求:\n"
            f"1. 用 Markdown，且只输出两个一级标题：`# {REVISION_ADVICE_SECTION_HEADING}` 与"
            f" `# {SESSION_INSTRUCTION_SECTION_HEADING}`。\n"
            "2. 第一部分面向用户，控制在 5 个二级小节以内，聚焦当前简历该删什么、该缩什么、该前置什么、该如何组合项目故事线。\n"
            "3. 第一部分必须单独包含“当前强调点调整建议”，明确说明模板里已有 underline 强调点哪些该保留、哪些该替换、哪些过度强调。\n"
            "4. 第一部分必须单独包含 Publications / References 的更新提醒，显式核对 Google Scholar 链接、Selected Publications 区块以及 reference.md 里的最新状态，尤其是 Accepted / preprint 条目。\n"
            "5. 第二部分是发给同一个 Codex session 的结构化 Markdown 指令，必须包含二级标题：`## 修改目标`、`## 必做项`、`## 事实核对`、`## 禁止项`、`## 完成定义`。\n"
            "6. 不要重复输出宏观岗位分析，不要复述 role.md，不要列出所有模板备选。\n"
            "7. 不要虚构任何项目、成果、论文状态或岗位要求。\n"
            "8. final message 只用 1-2 句中文总结这份岗位最该怎么改。\n"
        )
        return self._build_skill_prompt(
            title="Revision Advice",
            workspace=workspace,
            task_skill_key="revision_advice",
            allowed_write_paths=[workspace.revision_advice_path],
            specific_instructions=instructions,
        )

    def _build_session_start_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        return (
            "你正在执行 resume tailor workbench 的 Session Start。\n"
            "这一步不读取外部 skill 文件，而是使用内置的固定规则来建立或恢复同一个 Codex session。\n"
            f"唯一允许修改的目录: {workspace.workspace_dir}\n"
            f"工作区相对路径: {_safe_relative_path(workspace.workspace_dir, PARENT_ROOT)}\n"
            "不允许修改 .codex、.claude、asset、General、config 或其他工作区。\n"
            "role.md 是当前岗位信息的主文档；job_snapshot.json 只做留档，不是主输入。\n"
            "所有事实只能来自 role.md、user_notes.md、基础简历、projects.md、reference.md。\n"
            "final message 用 1-2 句简体中文总结。\n\n"
            f"<shared_skill>\n{EMBEDDED_SHARED_SKILL_TEXT}\n</shared_skill>\n\n"
            "本步骤目标：建立或恢复当前职位的 Codex session，后续直接在这个 session 里修改最终稿。\n"
            f"可读文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {workspace.base_resume_copy_path}\n"
            f"- {workspace.final_resume_path}\n- {PROJECT_LIBRARY_PATH}\n\n"
            "额外要求:\n"
            "1. 不要修改任何工作区文件。\n"
            "2. 只确认你已经理解当前 role、模板和最终稿路径。\n"
            f"3. 后续默认编辑文件是 {workspace.final_resume_path.name}。\n"
            "4. final message 只用 1-2 句中文确认 session 已就绪，并提醒用户可以直接发送 vibe 指令。\n"
        )

    def _build_session_prompt_instruction(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        instruction_text: str,
    ) -> str:
        optional_advice_block = ""
        if workspace.advice_path.exists():
            optional_advice_block += f"- {workspace.advice_path}\n"
        if workspace.revision_advice_path.exists():
            optional_advice_block += f"- {workspace.revision_advice_path}\n"
        instructions = (
            "本步骤目标：在当前同一个 session 内，根据结构化 Markdown 指令直接修改最终稿，并重新编译 PDF。\n"
            "这是当前已建立 Codex session 的 follow-up turn，不要重新 bootstrap，不要重复解释你已理解的工作区。\n"
            "默认沿用当前 session 对 role、notes、模板与 final tex 的记忆，只在需要核对事实时回看文件。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"{optional_advice_block}"
            f"- {workspace.final_resume_path}\n- {PROJECT_LIBRARY_PATH}\n"
            f"- {REFERENCE_LIBRARY_PATH}\n\n"
            f"允许修改的文件:\n- {workspace.final_resume_path}\n\n"
            f"用户本轮 Markdown 指令:\n{instruction_text.strip()}\n\n"
            "额外要求:\n"
            "1. 只修改最终 tex，不要改 role.md、advice、JSON 报告或其他目录。\n"
            "2. 可以调整 bullet、summary、publication/reference、顺序和措辞，但不能新增未证实事实。\n"
            "3. 保持 LaTeX 可编译。\n"
            "4. final message 只总结这一轮修改的重点。\n"
        )
        return self._build_skill_prompt(
            title="Session Prompt",
            workspace=workspace,
            task_skill_key="session_send",
            allowed_write_paths=[workspace.final_resume_path],
            specific_instructions=instructions,
        )

    def _ensure_asset_shortlist(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
    ) -> Path | None:
        try:
            return write_shortlist_for_workspace(
                job_description=f"{job.title}\n{job.profile_label}\n{job.description}",
                projects_path=PROJECT_LIBRARY_PATH,
                reference_path=REFERENCE_LIBRARY_PATH,
                output_path=workspace.asset_shortlist_path,
            )
        except OSError:
            return None

    def _build_matching_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        shortlist_path = self._ensure_asset_shortlist(job, workspace)
        shortlist_block = (
            f"- {shortlist_path}（基于岗位描述自动检索，作为快速参考；若不全面，仍以 projects.md / reference.md 为准）\n"
            if shortlist_path is not None and shortlist_path.exists()
            else ""
        )
        instructions = (
            "本步骤目标：生成 matching_analysis.json。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"{shortlist_block}"
            f"- {PROJECT_LIBRARY_PATH}\n- {REFERENCE_LIBRARY_PATH}\n\n"
            f"输出文件:\n- {workspace.matching_analysis_path}\n\n"
            "输出 JSON 必须符合以下 schema（所有 key 都必须出现）:\n"
            "```json\n"
            "{\n"
            '  "role_summary": "一句话概括岗位核心需求",\n'
            '  "core_dimensions": ["岗位看重的 2-4 个能力维度"],\n'
            '  "recommended_projects": [\n'
            "    {\n"
            '      "project_name": "项目名称（必须来自 projects.md）",\n'
            '      "relevance": "high | medium | low",\n'
            '      "reasoning": "为什么和岗位相关",\n'
            '      "suggested_emphasis": ["建议突出的 1-3 个技术点"]\n'
            "    }\n"
            "  ],\n"
            '  "drop_candidates": ["建议删减或弱化的项目名称"],\n'
            '  "keyword_mapping": {"岗位关键词": "简历中对应的表述"},\n'
            '  "story_arc": "2-3 句描述推荐的项目叙事主线"\n'
            "}\n"
            "```\n\n"
            "额外要求:\n"
            "1. 只做岗位-项目匹配，不要进入内容定制。\n"
            "2. 输出必须是合法 JSON，严格遵循上述 schema。\n"
            "3. 不要虚构项目、关键词或事实。\n"
            "4. final message 用 1-2 句总结推荐项目组合。\n"
        )
        return self._build_common_prompt(
            title=TAILOR_STEP_LABELS["matching"],
            workspace=workspace,
            step_rule_text=self.step_rule_texts["matching"],
            specific_instructions=instructions,
        )

    def _build_setup_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        instructions = (
            "本步骤目标：建立或恢复当前 job 的 Codex session，为后续步骤复用。\n"
            f"可读文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {workspace.base_resume_copy_path}\n\n"
            "额外要求:\n"
            "1. 不要创建、删除或修改任何工作区文件。\n"
            "2. 只做最小确认：你已经理解当前 job、role、notes 和 base resume 的位置。\n"
            "3. final message 只用 1-2 句中文确认 session 已就绪，并说明后续会继续在当前 session 内完成流水线。\n"
        )
        return self._build_common_prompt(
            title=TAILOR_STEP_LABELS["setup"],
            workspace=workspace,
            step_rule_text=self.step_rule_texts["setup"],
            specific_instructions=instructions,
        )

    def _build_content_tailor_prompt(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        attempt: int,
        issues_summary: str,
    ) -> str:
        previous_tailored = (
            f"- {workspace.tailored_resume_path}\n"
            if workspace.tailored_resume_path.exists()
            else ""
        )
        feedback_block = f"\n上轮问题反馈:\n{issues_summary}\n" if issues_summary else ""
        round_strategy = {
            1: (
                "本轮重点：大框架调整。\n"
                "- 重新排列项目顺序，把最相关的 2-3 个项目放在最前面。\n"
                "- 调整 summary/profile 段落，让开场直接对标岗位核心诉求。\n"
                "- 删除弱相关 bullet 或项目段，不要在措辞细节上花时间。\n"
            ),
            2: (
                "本轮重点：细节修正。\n"
                "- 精炼保留 bullet 的措辞，突出岗位关心的方法和成果。\n"
                "- 调整 underline 强调点，替换掉与岗位无关的强调。\n"
                "- 保持整体框架不变，只做段内优化。\n"
            ),
            3: (
                "本轮重点：最小化修复。\n"
                "- 只修复上一轮 fact-check 指出的具体问题。\n"
                "- 不要做任何额外的结构或措辞变动。\n"
                "- 如果 fact-check 问题涉及模糊边界，选择保守表述。\n"
            ),
        }.get(attempt, "")
        instructions = (
            f"这是 Tailor Loop 的第 {attempt} 轮 content-tailor。\n"
            f"{round_strategy}"
            "本轮目标：生成或覆盖 cv_tailored.tex。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {workspace.matching_analysis_path}\n"
            f"- {workspace.base_resume_copy_path}\n"
            f"{previous_tailored}"
            f"- {PROJECT_LIBRARY_PATH}\n\n"
            f"输出文件:\n- {workspace.tailored_resume_path}\n"
            f"{feedback_block}\n"
            "额外要求:\n"
            "1. 只修改 cv_tailored.tex，不要改 final tex。\n"
            "2. 严格基于 projects.md 和用户笔记，不要虚构项目表述。\n"
            "3. 允许重排 bullet、精炼 wording、增删个人陈述，但必须保持 LaTeX 可继续人工编辑。\n"
            "4. final message 只说明本轮改动重点。\n"
        )
        return self._build_common_prompt(
            title=f"{TAILOR_STEP_LABELS['tailor_loop']} / Content Tailor",
            workspace=workspace,
            step_rule_text=self.step_rule_texts["content_tailor"],
            specific_instructions=instructions,
        )

    def _build_fact_check_prompt(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        *,
        attempt: int,
    ) -> str:
        instructions = (
            f"这是 Tailor Loop 的第 {attempt} 轮 fact-check。\n"
            "本轮目标：生成 fact_check_report.json。\n"
            f"输入文件:\n- {workspace.tailored_resume_path}\n"
            f"- {workspace.role_path}\n- {PROJECT_LIBRARY_PATH}\n\n"
            f"输出文件:\n- {workspace.fact_check_report_path}\n\n"
            "额外要求:\n"
            "1. 输出必须是合法 JSON。\n"
            "2. 严格逐条校验 cv_tailored.tex 中的事实，不要直接改 tex。\n"
            "3. 如果发现问题，issues 里必须给出 content、issue、source_truth、recommendation。\n"
            "4. final message 只总结是否通过和问题数量。\n"
        )
        return self._build_common_prompt(
            title=f"{TAILOR_STEP_LABELS['tailor_loop']} / Fact Check",
            workspace=workspace,
            step_rule_text=self.step_rule_texts["fact_check"],
            specific_instructions=instructions,
        )

    def _build_final_proof_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        existing_final = (
            f"- {workspace.final_resume_path}\n"
            if workspace.final_resume_path.exists()
            else ""
        )
        soft_pass_todos_path = self._soft_pass_todos_path(workspace)
        soft_pass_input_line = (
            f"- {soft_pass_todos_path}\n" if soft_pass_todos_path.exists() else ""
        )
        soft_pass_instruction = (
            (
                "5. 存在 soft_pass_todos.md：tailor_loop 在第 3 轮仍有 ≤2 个 minor 问题。"
                "请将其中每条作为 `% TODO: <issue> -> <recommendation>` LaTeX 注释插入到 "
                "final tex 对应章节首行（同一行末尾或紧贴该章节下一行），便于人工复核时定位；"
                "不要把 TODO 内容直接写进可见的简历正文。\n"
            )
            if soft_pass_todos_path.exists()
            else ""
        )
        instructions = (
            "本步骤目标：写出最终 tex，不在这一步做整体 vibe review。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {workspace.matching_analysis_path}\n- {workspace.tailored_resume_path}\n"
            f"- {workspace.fact_check_report_path}\n- {REFERENCE_LIBRARY_PATH}\n"
            f"{soft_pass_input_line}{existing_final}\n"
            f"输出文件:\n- {workspace.final_resume_path}\n\n"
            "额外要求:\n"
            "1. 需要吸收 fact_check_report.json 的修复建议。\n"
            "2. 可以调整 references/publications，便于用户在 final proof 后继续微调文献。\n"
            "3. 不要生成 PDF；PDF 由本地服务负责编译。\n"
            "4. final message 只总结最终 tex 的重点变化。\n"
            f"{soft_pass_instruction}"
        )
        return self._build_common_prompt(
            title=TAILOR_STEP_LABELS["final_proof"],
            workspace=workspace,
            step_rule_text=self.step_rule_texts["final_proof"],
            specific_instructions=instructions,
        )

    def _build_final_prompt_instruction(
        self,
        job: JobRecord,
        workspace: TailorWorkspace,
        instruction_text: str,
    ) -> str:
        return self._build_session_prompt_instruction(job, workspace, instruction_text)

    def _build_vibe_review_prompt(self, job: JobRecord, workspace: TailorWorkspace) -> str:
        instructions = (
            "本步骤目标：对整份 final tex 做整体 vibe review，并直接修正最终稿。\n"
            f"输入文件:\n- {workspace.role_path}\n- {workspace.notes_path}\n"
            f"- {workspace.matching_analysis_path}\n- {workspace.fact_check_report_path}\n"
            f"- {workspace.final_resume_path}\n- {REFERENCE_LIBRARY_PATH}\n\n"
            f"输出文件:\n- {workspace.vibe_review_path}（先写）\n- {workspace.final_resume_path}（后改）\n\n"
            "严格执行顺序：\n"
            "步骤 1：先完整阅读 final tex，在 vibe_review.md 里列出所有需要改进的地方。\n"
            "步骤 2：基于 vibe_review.md 里列出的问题逐条修改 final tex。\n"
            "步骤 3：不要在改 tex 的同时回头修改 vibe_review.md 来与改动对齐。\n\n"
            "额外要求:\n"
            "1. vibe review 不是某一步局部微调，而是对整份 CV 的整体不足做 review。\n"
            "2. 可以指出并修正事实错误、proofreader 问题、文献问题或整体叙事问题。\n"
            "3. 如果某处看起来更强但事实依据不足，宁可不改。\n"
            "4. final message 只总结整体改进方向和是否修改了 references。\n"
        )
        return self._build_common_prompt(
            title=TAILOR_STEP_LABELS["vibe_review"],
            workspace=workspace,
            step_rule_text=self.step_rule_texts["vibe_review"],
            specific_instructions=instructions,
        )

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from glob import glob
from pathlib import Path

from app.config import ROOT_DIR, ResumeProfileConfig


@dataclass(frozen=True)
class ResumeProfile:
    name: str
    summary: str
    target_titles: tuple[str, ...]
    focus_domains: tuple[str, ...]
    weighted_keywords: dict[str, float]
    stop_keywords: tuple[str, ...]
    source_files: tuple[str, ...]
    resume_text: str


LATEX_COMMAND_RE = re.compile(r"\\[a-zA-Z*]+(?:\[[^\]]*\])?(?:\{([^{}]*)\})?")
MULTISPACE_RE = re.compile(r"\s+")


def _strip_latex_markup(text: str) -> str:
    # 这里不追求完整 LaTeX 解析，只做足够稳的简历文本提取。
    text = text.replace("\\&", " and ")
    text = text.replace("\\%", "%")
    text = text.replace("\\_", "_")
    text = text.replace("\\textsubscript", " ")
    text = LATEX_COMMAND_RE.sub(lambda match: match.group(1) or " ", text)
    text = text.replace("{", " ")
    text = text.replace("}", " ")
    text = text.replace("$", " ")
    return MULTISPACE_RE.sub(" ", text).strip()


def _expand_source_files(source_files: list[str]) -> list[Path]:
    expanded_files: list[Path] = []
    seen: set[Path] = set()

    for raw_path in source_files:
        matched_paths = [
            Path(path).resolve()
            for path in glob(str(ROOT_DIR / raw_path), recursive=True)
        ]
        if not matched_paths:
            matched_paths = [(ROOT_DIR / raw_path).resolve()]

        for file_path in sorted(matched_paths):
            if not file_path.exists() or file_path in seen:
                continue
            seen.add(file_path)
            expanded_files.append(file_path)

    return expanded_files


def build_resume_profile(config: ResumeProfileConfig) -> ResumeProfile:
    chunks: list[str] = []
    resolved_files: list[str] = []

    for file_path in _expand_source_files(config.source_files):
        resolved_files.append(Path(os.path.relpath(file_path, ROOT_DIR)).as_posix())
        chunks.append(_strip_latex_markup(file_path.read_text(encoding="utf-8")))

    combined_text = "\n".join(chunks)
    return ResumeProfile(
        name=config.name,
        summary=config.summary,
        target_titles=tuple(config.target_titles),
        focus_domains=tuple(config.focus_domains),
        weighted_keywords=dict(config.weighted_keywords),
        stop_keywords=tuple(config.stop_keywords),
        source_files=tuple(resolved_files),
        resume_text=combined_text,
    )

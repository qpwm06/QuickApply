from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

# 中文注释：用最小依赖实现 keyword + TF-IDF 检索；输入岗位描述，输出
# 资料库里最相关的项目段落和参考文献条目，供 matching prompt 复用。

_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9]+")
_STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this",
    "are", "was", "were", "have", "has", "had", "but", "not",
    "you", "your", "our", "their", "his", "her", "its", "they",
    "any", "all", "can", "will", "would", "should", "could",
    "such", "than", "then", "more", "most", "less", "many",
    "use", "used", "using", "via", "etc", "based", "across",
    "within", "without", "across", "between", "while", "after",
    "before", "during", "over", "under", "above", "below",
    "team", "teams", "role", "roles", "work", "working", "works",
    "year", "years", "month", "months", "day", "days",
    "experience", "experienced", "skills", "skill", "ability",
    "responsible", "responsibilities", "candidate", "candidates",
    "job", "position", "positions", "include", "includes", "including",
}


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [
        token.lower()
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) > 2 and token.lower() not in _STOP_WORDS
    ]


@dataclass(frozen=True)
class AssetSection:
    source: str
    heading: str
    body: str

    @property
    def tokens(self) -> list[str]:
        return _tokenize(f"{self.heading} {self.body}")


def _split_project_sections(text: str) -> list[AssetSection]:
    sections: list[AssetSection] = []
    if not text:
        return sections
    current_heading = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### ") and not stripped.startswith("####"):
            if current_heading:
                sections.append(
                    AssetSection(
                        source="projects.md",
                        heading=current_heading,
                        body="\n".join(current_lines).strip(),
                    )
                )
            current_heading = stripped[4:].strip()
            current_lines = []
            continue
        if current_heading:
            current_lines.append(line)
    if current_heading:
        sections.append(
            AssetSection(
                source="projects.md",
                heading=current_heading,
                body="\n".join(current_lines).strip(),
            )
        )
    return sections


def _split_reference_entries(text: str) -> list[AssetSection]:
    entries: list[AssetSection] = []
    if not text:
        return entries
    current_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            if current_lines:
                joined = "\n".join(current_lines).strip()
                if joined:
                    entries.append(
                        AssetSection(
                            source="reference.md",
                            heading=joined.splitlines()[0][:80],
                            body=joined,
                        )
                    )
            current_lines = [stripped[2:]]
        elif stripped:
            current_lines.append(stripped)
    if current_lines:
        joined = "\n".join(current_lines).strip()
        if joined:
            entries.append(
                AssetSection(
                    source="reference.md",
                    heading=joined.splitlines()[0][:80],
                    body=joined,
                )
            )
    return entries


def _tf_idf_scores(query_tokens: list[str], sections: list[AssetSection]) -> list[float]:
    if not sections or not query_tokens:
        return [0.0] * len(sections)

    doc_tokens = [section.tokens for section in sections]
    df: dict[str, int] = {}
    for tokens in doc_tokens:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    n = len(doc_tokens)
    idf = {token: math.log((n + 1) / (count + 1)) + 1.0 for token, count in df.items()}

    query_set = set(query_tokens)
    scores: list[float] = []
    for tokens in doc_tokens:
        if not tokens:
            scores.append(0.0)
            continue
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        score = 0.0
        for token in query_set:
            if token not in tf:
                continue
            score += tf[token] * idf.get(token, 1.0)
        scores.append(score / math.sqrt(len(tokens)))
    return scores


def shortlist(
    *,
    job_description: str,
    projects_text: str,
    reference_text: str,
    project_top_k: int = 5,
    reference_top_k: int = 6,
) -> dict[str, list[AssetSection]]:
    query_tokens = _tokenize(job_description)
    project_sections = _split_project_sections(projects_text)
    reference_sections = _split_reference_entries(reference_text)

    project_scores = _tf_idf_scores(query_tokens, project_sections)
    reference_scores = _tf_idf_scores(query_tokens, reference_sections)

    project_ranked = sorted(
        ((score, section) for score, section in zip(project_scores, project_sections) if score > 0),
        key=lambda pair: pair[0],
        reverse=True,
    )
    reference_ranked = sorted(
        ((score, section) for score, section in zip(reference_scores, reference_sections) if score > 0),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return {
        "projects": [section for _, section in project_ranked[:project_top_k]],
        "references": [section for _, section in reference_ranked[:reference_top_k]],
    }


def render_shortlist_markdown(shortlisted: dict[str, list[AssetSection]]) -> str:
    lines: list[str] = ["# Asset Shortlist", ""]
    lines.append(
        "> 这是基于岗位描述自动检索出的 projects.md / reference.md 片段，"
        "用作快速参考。原始文件仍是事实来源，必要时请回到原文件核对。"
    )
    lines.append("")

    projects = shortlisted.get("projects", [])
    if projects:
        lines.append("## 推荐项目片段")
        for index, section in enumerate(projects, start=1):
            lines.append(f"### {index}. {section.heading}")
            if section.body:
                lines.append(section.body)
            lines.append("")
    else:
        lines.append("## 推荐项目片段")
        lines.append("- 未检索到强相关项目，请回到 projects.md 全文判断。")
        lines.append("")

    references = shortlisted.get("references", [])
    if references:
        lines.append("## 推荐文献片段")
        for index, section in enumerate(references, start=1):
            lines.append(f"- {section.body}")
        lines.append("")
    else:
        lines.append("## 推荐文献片段")
        lines.append("- 未检索到强相关文献，请回到 reference.md 全文判断。")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_shortlist_for_workspace(
    *,
    job_description: str,
    projects_path: Path,
    reference_path: Path,
    output_path: Path,
    project_top_k: int = 5,
    reference_top_k: int = 6,
) -> Path:
    projects_text = projects_path.read_text(encoding="utf-8") if projects_path.exists() else ""
    reference_text = reference_path.read_text(encoding="utf-8") if reference_path.exists() else ""
    shortlisted = shortlist(
        job_description=job_description,
        projects_text=projects_text,
        reference_text=reference_text,
        project_top_k=project_top_k,
        reference_top_k=reference_top_k,
    )
    output_path.write_text(render_shortlist_markdown(shortlisted), encoding="utf-8")
    return output_path

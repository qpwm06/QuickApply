from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.config import SearchProfileConfig
from app.fetcher import FetchedJob
from app.resume_profile import ResumeProfile

TITLE_WEIGHT = 0.45
KEYWORD_WEIGHT = 0.30
DOMAIN_WEIGHT = 0.15
MARKET_WEIGHT = 0.10
STOP_KEYWORD_PENALTY = 0.18
# 中文注释：远程偏好做独立 ±5pp 调整，刻意不动主权重，避免回归既有权重不变量。
REMOTE_ALIGNMENT_BONUS = 0.05


@dataclass(frozen=True)
class ScoreBreakdown:
    total_score: float
    title_similarity: float
    keyword_coverage: float
    domain_similarity: float
    market_alignment: float
    penalty_applied: float
    remote_alignment: float
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    explanation: str


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _keyword_match(keyword: str, normalized_text: str) -> bool:
    """中文注释：关键词命中判定。
    单 token（纯字母/数字，没有空格、连字符、点号、斜杠等）走词界正则，避免
    "pytorch" 误命中 "pytorch3d"、"ml" 误命中 "html" 之类的子串问题。
    多 token 关键词（包含空格、连字符等）退化为子串匹配，因为 \b 在这些字符
    旁边的语义并不通用，强行加上反而会漏掉 "machine learning" 这类正常命中。
    """
    needle = normalize_text(keyword)
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9]+", needle):
        return re.search(rf"\b{re.escape(needle)}\b", normalized_text) is not None
    return needle in normalized_text


def _clamp_score(value: object, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, numeric))


def _market_alignment(
    job: FetchedJob,
    search_profile: SearchProfileConfig | None,
) -> float:
    if search_profile is None:
        return 0.5

    profile_priority = _clamp_score(search_profile.market_priority, 0.6)
    term_weight = _clamp_score(
        (search_profile.search_term_weights or {}).get(job.search_term, 1.0),
        1.0,
    )
    return round(profile_priority * 0.6 + term_weight * 0.4, 3)


def _remote_alignment(
    job: FetchedJob,
    search_profile: SearchProfileConfig | None,
) -> float:
    """中文注释：远程偏好返回 [-1.0, 1.0] 之间的对齐度，最终乘以 REMOTE_ALIGNMENT_BONUS。
    prefer + 远程岗位 → +1；avoid + 远程岗位 → -1；其他 → 0。
    job.is_remote 缺失时按非远程处理。"""
    if search_profile is None:
        return 0.0
    preference = (search_profile.remote_preference or "neutral").strip().lower()
    if preference not in {"prefer", "avoid"}:
        return 0.0
    is_remote = bool(getattr(job, "is_remote", False))
    if preference == "prefer":
        return 1.0 if is_remote else 0.0
    return -1.0 if is_remote else 0.0


def score_job(
    job: FetchedJob,
    profile: ResumeProfile,
    search_profile: SearchProfileConfig | None = None,
) -> ScoreBreakdown:
    # 中文注释：把标题、描述、地点放在同一个文本里，统一做关键词和领域匹配。
    full_text = normalize_text(
        " ".join(
            [
                job.title,
                job.company,
                job.location_text,
                job.city,
                job.state,
                job.description,
            ]
        )
    )
    title_text = normalize_text(job.title)

    title_similarity = 0.0
    if profile.target_titles:
        title_similarity = max(
            fuzz.token_set_ratio(title_text, normalize_text(target_title)) / 100.0
            for target_title in profile.target_titles
        )

    total_keyword_weight = sum(profile.weighted_keywords.values()) or 1.0
    matched_keywords: list[str] = []
    matched_weight = 0.0

    for keyword, weight in profile.weighted_keywords.items():
        if _keyword_match(keyword, full_text):
            matched_keywords.append(keyword)
            matched_weight += weight

    keyword_coverage = matched_weight / total_keyword_weight

    domain_similarity = 0.0
    if profile.focus_domains:
        domain_similarity = max(
            fuzz.partial_ratio(full_text, normalize_text(domain)) / 100.0
            for domain in profile.focus_domains
        )

    market_alignment = _market_alignment(job, search_profile)
    remote_alignment = _remote_alignment(job, search_profile)

    penalty_hits = [
        keyword
        for keyword in profile.stop_keywords
        if _keyword_match(keyword, full_text)
    ]
    penalty_applied = STOP_KEYWORD_PENALTY if penalty_hits else 0.0

    raw_score = (
        TITLE_WEIGHT * title_similarity
        + KEYWORD_WEIGHT * keyword_coverage
        + DOMAIN_WEIGHT * domain_similarity
        + MARKET_WEIGHT * market_alignment
        + REMOTE_ALIGNMENT_BONUS * remote_alignment
        - penalty_applied
    )
    total_score = max(0.0, min(100.0, round(raw_score * 100.0, 1)))

    missing_keywords = [
        keyword
        for keyword in profile.weighted_keywords
        if keyword not in matched_keywords
    ][:5]

    explanation_parts = [
        f"title={title_similarity:.2f}",
        f"keywords={keyword_coverage:.2f}",
        f"domain={domain_similarity:.2f}",
        f"market={market_alignment:.2f}",
    ]
    if remote_alignment:
        explanation_parts.append(f"remote={remote_alignment:+.2f}")
    if matched_keywords:
        explanation_parts.append(
            "matched=" + ", ".join(matched_keywords[:6])
        )
    if penalty_hits:
        explanation_parts.append("penalty=" + ", ".join(penalty_hits[:3]))

    return ScoreBreakdown(
        total_score=total_score,
        title_similarity=round(title_similarity, 3),
        keyword_coverage=round(keyword_coverage, 3),
        domain_similarity=round(domain_similarity, 3),
        market_alignment=round(market_alignment, 3),
        penalty_applied=round(penalty_applied, 3),
        remote_alignment=round(remote_alignment, 3),
        matched_keywords=tuple(matched_keywords[:8]),
        missing_keywords=tuple(missing_keywords),
        explanation=" | ".join(explanation_parts),
    )

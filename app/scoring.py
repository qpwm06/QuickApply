from __future__ import annotations

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


@dataclass(frozen=True)
class ScoreBreakdown:
    total_score: float
    title_similarity: float
    keyword_coverage: float
    domain_similarity: float
    market_alignment: float
    penalty_applied: float
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    explanation: str


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


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
        if normalize_text(keyword) in full_text:
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

    penalty_hits = [
        keyword
        for keyword in profile.stop_keywords
        if normalize_text(keyword) in full_text
    ]
    penalty_applied = STOP_KEYWORD_PENALTY if penalty_hits else 0.0

    raw_score = (
        TITLE_WEIGHT * title_similarity
        + KEYWORD_WEIGHT * keyword_coverage
        + DOMAIN_WEIGHT * domain_similarity
        + MARKET_WEIGHT * market_alignment
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
        matched_keywords=tuple(matched_keywords[:8]),
        missing_keywords=tuple(missing_keywords),
        explanation=" | ".join(explanation_parts),
    )

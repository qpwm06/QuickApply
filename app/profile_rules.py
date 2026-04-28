from __future__ import annotations

from collections.abc import Sequence
import re

from app.config import SearchProfileConfig
from app.fetcher import FetchedJob
from app.models import JobRecord

PROFILE_RULE_BREAK_RE = re.compile(r"[^a-z0-9]+")


def normalize_profile_rule_text(value: str) -> str:
    lowered = str(value or "").lower()
    normalized = PROFILE_RULE_BREAK_RE.sub(" ", lowered)
    return " ".join(normalized.split())


def normalize_profile_rule_terms(values: Sequence[str] | None) -> tuple[str, ...]:
    normalized_terms: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        normalized = normalize_profile_rule_text(str(value))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_terms.append(normalized)
    return tuple(normalized_terms)


def build_profile_rule_blob(*parts: str) -> str:
    # 中文注释：这里专门把职位文本压成统一的小写短语，避免 single-cell / single cell
    # 这类写法差异导致的误判。
    return normalize_profile_rule_text(" ".join(str(part or "") for part in parts))


def matches_profile_rule_blob(
    rule_blob: str,
    *,
    exclude_keywords: Sequence[str] | None = None,
    require_any_keywords: Sequence[str] | None = None,
) -> bool:
    exclude_terms = normalize_profile_rule_terms(exclude_keywords)
    required_terms = normalize_profile_rule_terms(require_any_keywords)

    if exclude_terms and any(term in rule_blob for term in exclude_terms):
        return False
    if required_terms and not any(term in rule_blob for term in required_terms):
        return False
    return True


def matches_search_profile_rules(
    rule_blob: str,
    search_profile: SearchProfileConfig | None,
) -> bool:
    if search_profile is None:
        return True
    return matches_profile_rule_blob(
        rule_blob,
        exclude_keywords=search_profile.exclude_keywords,
        require_any_keywords=search_profile.require_any_keywords,
    )


def build_fetched_job_rule_blob(job: FetchedJob) -> str:
    return build_profile_rule_blob(
        job.title,
        job.company,
        job.search_term,
        job.location_text,
        job.city,
        job.state,
        job.country,
        job.description,
    )


def build_job_record_rule_blob(job: JobRecord) -> str:
    return build_profile_rule_blob(
        job.title,
        job.company,
        job.search_term,
        job.location_text,
        job.city,
        job.state,
        job.country,
        job.description,
    )

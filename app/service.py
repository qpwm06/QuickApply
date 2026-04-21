from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from app.config import SearchProfileConfig, Settings
from app.fetcher import JobSpyFetcher
from app.models import JobRecord, RefreshRun
from app.resume_profile import ResumeProfile
from app.scoring import score_job
from app.storage import JobRepository


@dataclass(frozen=True)
class RefreshOutcome:
    profile_slug: str
    profile_label: str
    jobs_seen: int
    jobs_saved: int
    warnings: tuple[str, ...]
    query_details: tuple[dict[str, object], ...]
    started_at: datetime
    finished_at: datetime


class JobMonitorService:
    def __init__(
        self,
        settings: Settings,
        resume_profile: ResumeProfile,
        repository: JobRepository,
        fetcher: JobSpyFetcher,
    ) -> None:
        self.settings = settings
        self.resume_profile = resume_profile
        self.repository = repository
        self.fetcher = fetcher
        self.profile_map = {
            profile.slug: profile
            for profile in settings.search_profiles
            if profile.enabled
        }

    def enabled_profiles(self) -> list[SearchProfileConfig]:
        return list(self.profile_map.values())

    def refresh_all(self) -> list[RefreshOutcome]:
        return [self.refresh_profile(profile.slug) for profile in self.enabled_profiles()]

    def refresh_profile(self, profile_slug: str) -> RefreshOutcome:
        profile = self.profile_map[profile_slug]
        started_at = datetime.now(timezone.utc)
        fetched_jobs, warnings, query_details = self.fetcher.fetch_profile(profile)

        scored_records: list[JobRecord] = []
        for job in fetched_jobs:
            breakdown = score_job(job, self.resume_profile, profile)
            if breakdown.total_score < self.settings.app.min_score_to_store:
                continue

            scored_records.append(
                JobRecord(
                    unique_key=job.unique_key,
                    profile_slug=profile.slug,
                    profile_label=profile.label,
                    search_term=job.search_term,
                    source_site=job.source_site,
                    title=job.title,
                    company=job.company,
                    location_text=job.location_text,
                    city=job.city,
                    state=job.state,
                    country=job.country,
                    job_url=job.job_url,
                    company_url=job.company_url,
                    interval=job.interval,
                    currency=job.currency,
                    min_amount=job.min_amount,
                    max_amount=job.max_amount,
                    is_remote=job.is_remote,
                    score=breakdown.total_score,
                    title_similarity=breakdown.title_similarity,
                    keyword_coverage=breakdown.keyword_coverage,
                    domain_similarity=breakdown.domain_similarity,
                    market_alignment=breakdown.market_alignment,
                    penalty_applied=breakdown.penalty_applied,
                    matched_keywords=", ".join(breakdown.matched_keywords),
                    missing_keywords=", ".join(breakdown.missing_keywords),
                    explanation=breakdown.explanation,
                    description=job.description,
                    date_posted=job.date_posted,
                )
            )

        jobs_saved = self.repository.upsert_jobs(scored_records)
        finished_at = datetime.now(timezone.utc)

        self.repository.record_refresh_run(
            RefreshRun(
                profile_slug=profile.slug,
                profile_label=profile.label,
                started_at=started_at,
                finished_at=finished_at,
                success=not warnings,
                jobs_seen=len(fetched_jobs),
                jobs_saved=jobs_saved,
                warnings_text="\n".join(warnings),
                result_json=json.dumps(
                    {
                        "profile_slug": profile.slug,
                        "profile_label": profile.label,
                        "requested_sites": list(profile.sites),
                        "warnings": list(warnings),
                        "query_details": list(query_details),
                    },
                    ensure_ascii=False,
                ),
            )
        )

        return RefreshOutcome(
            profile_slug=profile.slug,
            profile_label=profile.label,
            jobs_seen=len(fetched_jobs),
            jobs_saved=jobs_saved,
            warnings=tuple(warnings),
            query_details=tuple(query_details),
            started_at=started_at,
            finished_at=finished_at,
        )

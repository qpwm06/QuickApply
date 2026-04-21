from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from sqlalchemy import desc, func, or_
from sqlmodel import Session, SQLModel, create_engine, select

from app.location_utils import COUNTRY_FILTER_OPTIONS, job_country_label, matches_location_query
from app.models import (
    ApplicationTrack,
    ApplicationTrackEvent,
    ExcludedCompany,
    JobRecord,
    RefreshRun,
    TailorRun,
    TailorRunStep,
)


def normalize_company_name(company: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", company.strip().lower())
    return " ".join(normalized.split())


def normalize_keyword_terms(keywords: Sequence[str] | None) -> tuple[str, ...]:
    normalized_terms: list[str] = []
    seen: set[str] = set()
    for keyword in keywords or ():
        normalized = " ".join(str(keyword).strip().lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_terms.append(normalized)
    return tuple(normalized_terms)


def build_job_keyword_blob(job: JobRecord) -> str:
    return "\n".join(
        [
            job.title,
            job.company,
            job.location_text,
            job.description,
            job.matched_keywords,
            job.search_term,
        ]
    ).lower()


def matches_keyword_filters(
    job: JobRecord,
    *,
    include_keywords: Sequence[str] | None = None,
    exclude_keywords: Sequence[str] | None = None,
) -> bool:
    include_terms = normalize_keyword_terms(include_keywords)
    exclude_terms = normalize_keyword_terms(exclude_keywords)
    if not include_terms and not exclude_terms:
        return True

    keyword_blob = build_job_keyword_blob(job)
    if exclude_terms and any(term in keyword_blob for term in exclude_terms):
        return False
    if include_terms and not any(term in keyword_blob for term in include_terms):
        return False
    return True


class JobRepository:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite:///"):
            sqlite_path = Path(database_url.removeprefix("sqlite:///"))
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)

    def init_db(self) -> None:
        SQLModel.metadata.create_all(self.engine)
        self._ensure_sqlite_schema()

    def _ensure_sqlite_schema(self) -> None:
        if not str(self.engine.url).startswith("sqlite"):
            return
        with self.engine.begin() as connection:
            self._ensure_columns(
                connection,
                getattr(JobRecord, "__tablename__", "jobrecord"),
                {
                    "applied_at": "DATETIME",
                    "dismissed_at": "DATETIME",
                    "market_alignment": "FLOAT",
                },
            )
            self._ensure_columns(
                connection,
                getattr(ApplicationTrack, "__tablename__", "applicationtrack"),
                {
                    "current_stage": "TEXT DEFAULT 'submitted'",
                    "current_stage_at": "DATETIME",
                    "latest_notes": "TEXT DEFAULT ''",
                },
            )
            self._ensure_columns(
                connection,
                getattr(TailorRun, "__tablename__", "tailorrun"),
                {
                    "session_id": "TEXT DEFAULT ''",
                    "current_step_key": "TEXT DEFAULT ''",
                    "current_pid": "INTEGER",
                },
            )
            self._ensure_columns(
                connection,
                getattr(RefreshRun, "__tablename__", "refreshrun"),
                {
                    "result_json": "TEXT DEFAULT ''",
                },
            )

    def _ensure_columns(
        self,
        connection,
        table_name: str,
        required_columns: dict[str, str],
    ) -> None:
        rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
        column_names = {row[1] for row in rows}
        for column_name, column_sql in required_columns.items():
            if column_name in column_names:
                continue
            connection.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
            )

    def upsert_jobs(self, jobs: Sequence[JobRecord]) -> int:
        if not jobs:
            return 0

        keys = [job.unique_key for job in jobs]
        now = datetime.now(timezone.utc)

        with Session(self.engine) as session:
            existing_records = session.exec(
                select(JobRecord).where(JobRecord.unique_key.in_(keys))
            ).all()
            existing_by_key = {record.unique_key: record for record in existing_records}
            saved = 0

            for job in jobs:
                current = existing_by_key.get(job.unique_key)
                if current is None:
                    job.first_seen_at = now
                    job.last_seen_at = now
                    job.last_refreshed_at = now
                    session.add(job)
                    saved += 1
                    continue

                # 中文注释：同一职位重复抓到时保留首次发现时间，只更新动态字段。
                current.profile_slug = job.profile_slug
                current.profile_label = job.profile_label
                current.search_term = job.search_term
                current.source_site = job.source_site
                current.title = job.title
                current.company = job.company
                current.location_text = job.location_text
                current.city = job.city
                current.state = job.state
                current.country = job.country
                current.job_url = job.job_url
                current.company_url = job.company_url
                current.interval = job.interval
                current.currency = job.currency
                current.min_amount = job.min_amount
                current.max_amount = job.max_amount
                current.is_remote = job.is_remote
                current.score = job.score
                current.title_similarity = job.title_similarity
                current.keyword_coverage = job.keyword_coverage
                current.domain_similarity = job.domain_similarity
                current.market_alignment = job.market_alignment
                current.penalty_applied = job.penalty_applied
                current.matched_keywords = job.matched_keywords
                current.missing_keywords = job.missing_keywords
                current.explanation = job.explanation
                current.description = job.description
                current.date_posted = job.date_posted
                current.last_seen_at = now
                current.last_refreshed_at = now
                saved += 1

            session.commit()
            return saved

    def record_refresh_run(self, run: RefreshRun) -> None:
        persisted = RefreshRun(
            profile_slug=run.profile_slug,
            profile_label=run.profile_label,
            started_at=run.started_at,
            finished_at=run.finished_at,
            success=run.success,
            jobs_seen=run.jobs_seen,
            jobs_saved=run.jobs_saved,
            warnings_text=run.warnings_text,
            result_json=run.result_json,
        )
        with Session(self.engine) as session:
            session.add(persisted)
            session.commit()

    def get_refresh_run(self, run_id: int) -> RefreshRun | None:
        with Session(self.engine) as session:
            return session.get(RefreshRun, run_id)

    def list_jobs(
        self,
        *,
        profile_slug: str | None = None,
        min_score: float = 0.0,
        limit: int = 60,
        countries: Sequence[str] | None = None,
        location_query: str = "",
        include_keywords: Sequence[str] | None = None,
        exclude_keywords: Sequence[str] | None = None,
        recent_hours: int = 0,
        sort_by: str = "recent",
    ) -> list[JobRecord]:
        jobs = self._load_filtered_jobs(
            profile_slug=profile_slug,
            min_score=min_score,
            countries=countries,
            location_query=location_query,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            recent_hours=recent_hours,
            sort_by=sort_by,
        )
        remaining_jobs = [
            job for job in jobs if job.applied_at is None and job.dismissed_at is None
        ]
        return remaining_jobs[:limit]

    def jobs_filter_counts(
        self,
        *,
        profile_slug: str | None = None,
        min_score: float = 0.0,
        countries: Sequence[str] | None = None,
        location_query: str = "",
        include_keywords: Sequence[str] | None = None,
        exclude_keywords: Sequence[str] | None = None,
        recent_hours: int = 0,
        sort_by: str = "recent",
    ) -> dict[str, int]:
        jobs = self._load_filtered_jobs(
            profile_slug=profile_slug,
            min_score=min_score,
            countries=countries,
            location_query=location_query,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            recent_hours=recent_hours,
            sort_by=sort_by,
        )
        counts = {
            "remaining_count": 0,
            "applied_count": 0,
            "reviewed_count": 0,
        }
        for job in jobs:
            is_applied = job.applied_at is not None
            is_dismissed = job.dismissed_at is not None
            if not is_applied and not is_dismissed:
                counts["remaining_count"] += 1
            if is_applied:
                counts["applied_count"] += 1
            if is_applied or is_dismissed:
                counts["reviewed_count"] += 1
        return counts

    def _build_jobs_statement(
        self,
        *,
        profile_slug: str | None = None,
        min_score: float = 0.0,
        recent_hours: int = 0,
        sort_by: str = "recent",
    ):
        statement = select(JobRecord).where(JobRecord.score >= min_score)
        if profile_slug:
            statement = statement.where(JobRecord.profile_slug == profile_slug)
        if recent_hours > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=recent_hours)
            statement = statement.where(JobRecord.last_refreshed_at >= cutoff)
        if sort_by == "score":
            return statement.order_by(desc(JobRecord.score), desc(JobRecord.last_refreshed_at))
        return statement.order_by(desc(JobRecord.last_refreshed_at), desc(JobRecord.score))

    def _load_filtered_jobs(
        self,
        *,
        profile_slug: str | None = None,
        min_score: float = 0.0,
        countries: Sequence[str] | None = None,
        location_query: str = "",
        include_keywords: Sequence[str] | None = None,
        exclude_keywords: Sequence[str] | None = None,
        recent_hours: int = 0,
        sort_by: str = "recent",
    ) -> list[JobRecord]:
        statement = self._build_jobs_statement(
            profile_slug=profile_slug,
            min_score=min_score,
            recent_hours=recent_hours,
            sort_by=sort_by,
        )

        with Session(self.engine) as session:
            rows = list(session.exec(statement).all())
            excluded_names = {
                item.normalized_name for item in session.exec(select(ExcludedCompany)).all()
            }

        selected_countries = {country for country in (countries or []) if country}
        filtered: list[JobRecord] = []
        for job in rows:
            if normalize_company_name(job.company) in excluded_names:
                continue
            if selected_countries and job_country_label(job) not in selected_countries:
                continue
            if location_query and not matches_location_query(job, location_query):
                continue
            if not matches_keyword_filters(
                job,
                include_keywords=include_keywords,
                exclude_keywords=exclude_keywords,
            ):
                continue
            filtered.append(job)
        return filtered

    def list_excluded_companies(self) -> list[ExcludedCompany]:
        statement = select(ExcludedCompany).order_by(
            ExcludedCompany.display_name,
            ExcludedCompany.created_at,
        )
        with Session(self.engine) as session:
            return list(session.exec(statement).all())

    def create_excluded_company(self, company_name: str) -> ExcludedCompany:
        normalized_name = normalize_company_name(company_name)
        if not normalized_name:
            raise ValueError("company name is required")

        display_name = " ".join(company_name.split())
        with Session(self.engine) as session:
            existing = session.exec(
                select(ExcludedCompany).where(
                    ExcludedCompany.normalized_name == normalized_name
                )
            ).first()
            if existing is not None:
                return existing

            item = ExcludedCompany(
                display_name=display_name,
                normalized_name=normalized_name,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def delete_excluded_company(self, company_id: int) -> bool:
        with Session(self.engine) as session:
            item = session.get(ExcludedCompany, company_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def is_company_excluded(self, company_name: str) -> bool:
        normalized_name = normalize_company_name(company_name)
        if not normalized_name:
            return False
        with Session(self.engine) as session:
            return (
                session.exec(
                    select(ExcludedCompany).where(
                        ExcludedCompany.normalized_name == normalized_name
                    )
                ).first()
                is not None
            )

    def get_job(self, job_id: int) -> JobRecord | None:
        with Session(self.engine) as session:
            return session.get(JobRecord, job_id)

    def sync_profile_labels(self, profile_labels: dict[str, str]) -> None:
        if not profile_labels:
            return
        with Session(self.engine) as session:
            for job in session.exec(select(JobRecord)).all():
                next_label = profile_labels.get(job.profile_slug)
                if next_label and job.profile_label != next_label:
                    job.profile_label = next_label
                    session.add(job)
            for track in session.exec(select(ApplicationTrack)).all():
                next_label = profile_labels.get(track.profile_slug)
                if next_label and track.profile_label != next_label:
                    track.profile_label = next_label
                    session.add(track)
            for run in session.exec(select(RefreshRun)).all():
                next_label = profile_labels.get(run.profile_slug)
                if next_label and run.profile_label != next_label:
                    run.profile_label = next_label
                    session.add(run)
            session.commit()

    def dismiss_job(self, job_id: int, *, dismissed_at: datetime | None) -> JobRecord | None:
        with Session(self.engine) as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                return None
            job.dismissed_at = dismissed_at
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def update_job_application(
        self,
        job_id: int,
        *,
        applied_at: datetime | None,
    ) -> JobRecord | None:
        with Session(self.engine) as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                return None
            job.applied_at = applied_at
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def overview_counts(self) -> dict[str, int]:
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        with Session(self.engine) as session:
            total_jobs = session.exec(select(func.count()).select_from(JobRecord)).one()
            strong_matches = session.exec(
                select(func.count()).select_from(JobRecord).where(JobRecord.score >= 65)
            ).one()
            recent_jobs = session.exec(
                select(func.count()).select_from(JobRecord).where(
                    JobRecord.last_seen_at >= seven_days_ago
                )
            ).one()
            applied_jobs = session.exec(
                select(func.count()).select_from(JobRecord).where(JobRecord.applied_at.is_not(None))
            ).one()

        return {
            "total_jobs": int(total_jobs or 0),
            "strong_matches": int(strong_matches or 0),
            "recent_jobs": int(recent_jobs or 0),
            "applied_jobs": int(applied_jobs or 0),
        }

    def list_applied_jobs(self, limit: int = 8) -> list[JobRecord]:
        statement = (
            select(JobRecord)
            .where(JobRecord.applied_at.is_not(None))
            .order_by(desc(JobRecord.applied_at), desc(JobRecord.last_refreshed_at))
            .limit(limit)
        )
        with Session(self.engine) as session:
            return list(session.exec(statement).all())

    def sync_application_track_for_job(
        self,
        job_id: int,
        *,
        applied_at: datetime | None,
    ) -> ApplicationTrack | None:
        with Session(self.engine) as session:
            job = session.get(JobRecord, job_id)
            if job is None:
                return None

            track = session.exec(
                select(ApplicationTrack).where(ApplicationTrack.job_id == job_id)
            ).first()

            job.applied_at = applied_at
            session.add(job)

            if applied_at is None:
                if track is not None:
                    for event in session.exec(
                        select(ApplicationTrackEvent).where(ApplicationTrackEvent.track_id == track.id)
                    ).all():
                        session.delete(event)
                    session.delete(track)
                session.commit()
                return None

            is_new_track = track is None
            if track is None:
                track = ApplicationTrack(job_id=job_id, source_kind="linked")

            track.title = job.title
            track.company = job.company
            track.source_site = job.source_site
            track.profile_slug = job.profile_slug
            track.profile_label = job.profile_label
            track.job_url = job.job_url
            track.current_stage = track.current_stage or "submitted"
            track.current_stage_at = track.current_stage_at or applied_at
            track.latest_notes = track.latest_notes or ""
            track.applied_at = applied_at
            track.updated_at = datetime.now(timezone.utc)
            session.add(track)
            session.commit()
            session.refresh(track)
            if is_new_track:
                self.add_application_track_event(
                    track.id or 0,
                    stage="submitted",
                    occurred_at=applied_at,
                    notes="",
                )
            return track

    def create_manual_application_track(self, track: ApplicationTrack) -> ApplicationTrack:
        now = datetime.now(timezone.utc)
        track.source_kind = "manual"
        track.created_at = now
        track.updated_at = now
        track.current_stage = track.current_stage or "submitted"
        track.current_stage_at = track.current_stage_at or track.applied_at
        track.latest_notes = track.latest_notes or track.notes
        with Session(self.engine) as session:
            session.add(track)
            session.commit()
            session.refresh(track)
            created = track
        self.add_application_track_event(
            created.id or 0,
            stage=created.current_stage,
            occurred_at=created.current_stage_at or created.applied_at,
            notes=created.notes,
        )
        return created

    def delete_application_track(self, track_id: int) -> bool:
        with Session(self.engine) as session:
            track = session.get(ApplicationTrack, track_id)
            if track is None:
                return False
            for event in session.exec(
                select(ApplicationTrackEvent).where(ApplicationTrackEvent.track_id == track_id)
            ).all():
                session.delete(event)
            session.delete(track)
            session.commit()
            return True

    def get_application_track(self, track_id: int) -> ApplicationTrack | None:
        with Session(self.engine) as session:
            return session.get(ApplicationTrack, track_id)

    def list_application_track_events(self, track_id: int) -> list[ApplicationTrackEvent]:
        statement = (
            select(ApplicationTrackEvent)
            .where(ApplicationTrackEvent.track_id == track_id)
            .order_by(ApplicationTrackEvent.occurred_at, ApplicationTrackEvent.created_at)
        )
        with Session(self.engine) as session:
            return list(session.exec(statement).all())

    def add_application_track_event(
        self,
        track_id: int,
        *,
        stage: str,
        occurred_at: datetime,
        notes: str,
    ) -> ApplicationTrackEvent | None:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            track = session.get(ApplicationTrack, track_id)
            if track is None:
                return None

            event = ApplicationTrackEvent(
                track_id=track_id,
                stage=stage,
                occurred_at=occurred_at,
                notes=notes,
                created_at=now,
            )
            track.current_stage = stage
            track.current_stage_at = occurred_at
            track.latest_notes = notes
            track.updated_at = now
            session.add(event)
            session.add(track)
            session.commit()
            session.refresh(event)
            return event

    def list_application_tracks(
        self,
        *,
        source_kind: str | None = None,
        keyword: str | None = None,
        stage: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        statement = select(ApplicationTrack, JobRecord).join(
            JobRecord, JobRecord.id == ApplicationTrack.job_id, isouter=True
        )
        if source_kind:
            statement = statement.where(ApplicationTrack.source_kind == source_kind)
        if stage:
            statement = statement.where(ApplicationTrack.current_stage == stage)
        normalized_keyword = " ".join((keyword or "").strip().lower().split())
        if normalized_keyword:
            statement = statement.where(
                or_(
                    func.lower(ApplicationTrack.title).contains(normalized_keyword),
                    func.lower(ApplicationTrack.company).contains(normalized_keyword),
                )
            )
        statement = statement.order_by(
            desc(ApplicationTrack.current_stage_at),
            desc(ApplicationTrack.applied_at),
            desc(ApplicationTrack.updated_at),
        ).limit(limit)

        with Session(self.engine) as session:
            rows = session.exec(statement).all()
            track_ids = [track.id for track, _ in rows if track.id is not None]
            event_rows = session.exec(
                select(ApplicationTrackEvent)
                .where(ApplicationTrackEvent.track_id.in_(track_ids))
                .order_by(
                    ApplicationTrackEvent.track_id,
                    ApplicationTrackEvent.occurred_at,
                    ApplicationTrackEvent.created_at,
                )
            ).all() if track_ids else []

        events_by_track: dict[int, list[ApplicationTrackEvent]] = defaultdict(list)
        for event in event_rows:
            if event.track_id is not None:
                events_by_track[event.track_id].append(event)

        return [
            {
                "track": track,
                "job": job,
                "events": events_by_track.get(track.id or 0, []),
            }
            for track, job in rows
        ]

    def application_track_stats(self) -> dict[str, int]:
        statement = (
            select(ApplicationTrack.source_kind, func.count(ApplicationTrack.id))
            .group_by(ApplicationTrack.source_kind)
        )
        with Session(self.engine) as session:
            rows = session.exec(statement).all()

        stats = {
            "total": 0,
            "linked": 0,
            "manual": 0,
        }
        for source_kind, count in rows:
            count_value = int(count or 0)
            stats["total"] += count_value
            if source_kind in stats:
                stats[source_kind] = count_value
        return stats

    def profile_stats(self) -> list[dict[str, object]]:
        statement = (
            select(
                JobRecord.profile_slug,
                JobRecord.profile_label,
                func.count(JobRecord.id),
                func.max(JobRecord.score),
                func.max(JobRecord.last_refreshed_at),
            )
            .group_by(JobRecord.profile_slug, JobRecord.profile_label)
            .order_by(desc(func.max(JobRecord.last_refreshed_at)))
        )
        source_statement = (
            select(
                JobRecord.profile_slug,
                JobRecord.source_site,
                func.count(JobRecord.id),
            )
            .group_by(JobRecord.profile_slug, JobRecord.source_site)
            .order_by(JobRecord.profile_slug, desc(func.count(JobRecord.id)))
        )

        with Session(self.engine) as session:
            rows = session.exec(statement).all()
            source_rows = session.exec(source_statement).all()

        source_map: dict[str, list[dict[str, object]]] = defaultdict(list)
        for profile_slug, source_site, job_count in source_rows:
            source_map[profile_slug].append(
                {
                    "source_site": source_site,
                    "job_count": int(job_count or 0),
                }
            )

        return [
            {
                "profile_slug": row[0],
                "profile_label": row[1],
                "job_count": int(row[2] or 0),
                "best_score": float(row[3] or 0.0),
                "last_refresh": row[4],
                "source_sites": source_map.get(row[0], []),
            }
            for row in rows
        ]

    def source_site_overview(self, *, profile_slug: str | None = None) -> list[dict[str, object]]:
        statement = (
            select(
                JobRecord.source_site,
                func.count(JobRecord.id),
                func.max(JobRecord.last_seen_at),
            )
            .group_by(JobRecord.source_site)
            .order_by(desc(func.count(JobRecord.id)), JobRecord.source_site)
        )
        if profile_slug:
            statement = statement.where(JobRecord.profile_slug == profile_slug)

        with Session(self.engine) as session:
            rows = session.exec(statement).all()

        return [
            {
                "source_site": row[0],
                "job_count": int(row[1] or 0),
                "last_seen_at": row[2],
            }
            for row in rows
        ]

    def latest_refresh_runs(self, limit: int = 8) -> list[RefreshRun]:
        statement = select(RefreshRun).order_by(desc(RefreshRun.started_at)).limit(limit)
        with Session(self.engine) as session:
            return list(session.exec(statement).all())

    def country_stats(self, *, profile_slug: str | None = None) -> list[dict[str, object]]:
        statement = select(JobRecord)
        if profile_slug:
            statement = statement.where(JobRecord.profile_slug == profile_slug)

        with Session(self.engine) as session:
            rows = list(session.exec(statement).all())

        counts = {option: 0 for option in COUNTRY_FILTER_OPTIONS}
        for job in rows:
            counts[job_country_label(job)] += 1

        return [
            {
                "country": option,
                "job_count": counts[option],
            }
            for option in COUNTRY_FILTER_OPTIONS
        ]

    def create_tailor_run(self, run: TailorRun) -> TailorRun:
        now = datetime.now(timezone.utc)
        run.created_at = now
        run.updated_at = now
        with Session(self.engine) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def update_tailor_run(self, run_id: int, **fields: object) -> TailorRun | None:
        with Session(self.engine) as session:
            run = session.get(TailorRun, run_id)
            if run is None:
                return None

            for key, value in fields.items():
                setattr(run, key, value)
            run.updated_at = datetime.now(timezone.utc)
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get_tailor_run(self, run_id: int) -> TailorRun | None:
        with Session(self.engine) as session:
            return session.get(TailorRun, run_id)

    def delete_tailor_run(self, run_id: int) -> bool:
        with Session(self.engine) as session:
            run = session.get(TailorRun, run_id)
            if run is None:
                return False
            for step in session.exec(
                select(TailorRunStep).where(TailorRunStep.run_id == run_id)
            ).all():
                session.delete(step)
            session.delete(run)
            session.commit()
            return True

    def latest_tailor_run_for_job(self, job_id: int) -> TailorRun | None:
        statement = (
            select(TailorRun)
            .where(TailorRun.job_id == job_id)
            .order_by(desc(TailorRun.created_at))
            .limit(1)
        )
        with Session(self.engine) as session:
            return session.exec(statement).first()

    def list_tailor_runs_for_job(self, job_id: int, limit: int = 6) -> list[TailorRun]:
        statement = (
            select(TailorRun)
            .where(TailorRun.job_id == job_id)
            .order_by(desc(TailorRun.created_at))
            .limit(limit)
        )
        with Session(self.engine) as session:
            return list(session.exec(statement).all())

    def upsert_tailor_run_step(
        self,
        run_id: int,
        step_key: str,
        **fields: object,
    ) -> TailorRunStep:
        with Session(self.engine) as session:
            step = session.exec(
                select(TailorRunStep)
                .where(TailorRunStep.run_id == run_id, TailorRunStep.step_key == step_key)
            ).first()
            if step is None:
                step = TailorRunStep(
                    run_id=run_id,
                    step_key=step_key,
                    created_at=datetime.now(timezone.utc),
                )
            for key, value in fields.items():
                setattr(step, key, value)
            session.add(step)
            session.commit()
            session.refresh(step)
            return step

    def list_tailor_run_steps(self, run_id: int) -> list[TailorRunStep]:
        statement = (
            select(TailorRunStep)
            .where(TailorRunStep.run_id == run_id)
            .order_by(TailorRunStep.created_at, TailorRunStep.id)
        )
        with Session(self.engine) as session:
            return list(session.exec(statement).all())

    def list_tailor_runs(
        self,
        *,
        status: str | None = None,
        profile_slug: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        statement = (
            select(TailorRun, JobRecord)
            .join(JobRecord, JobRecord.id == TailorRun.job_id, isouter=True)
            .order_by(desc(TailorRun.created_at))
            .limit(limit)
        )
        if status:
            statement = statement.where(TailorRun.status == status)
        if profile_slug:
            statement = statement.where(TailorRun.profile_slug == profile_slug)

        with Session(self.engine) as session:
            rows = session.exec(statement).all()

        results: list[dict[str, object]] = []
        for run, job in rows:
            results.append(
                {
                    "run": run,
                    "job": job,
                    "result": self.decode_tailor_result(run),
                    "steps": self.list_tailor_run_steps(run.id or 0),
                }
            )
        return results

    def tailor_run_stats(self) -> dict[str, int]:
        statement = select(TailorRun.status, func.count(TailorRun.id)).group_by(TailorRun.status)
        with Session(self.engine) as session:
            rows = session.exec(statement).all()

        stats = {
            "total": 0,
            "pending": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "stopped": 0,
        }
        for status, count in rows:
            count_value = int(count or 0)
            stats["total"] += count_value
            if status in stats:
                stats[status] = count_value
        return stats

    def decode_tailor_result(self, run: TailorRun | None) -> dict[str, object]:
        if run is None or not run.result_json:
            return {}
        try:
            return json.loads(run.result_json)
        except json.JSONDecodeError:
            return {}

    def decode_refresh_result(self, run: RefreshRun | None) -> dict[str, object]:
        if run is None or not run.result_json:
            return {}
        try:
            return json.loads(run.result_json)
        except json.JSONDecodeError:
            return {}

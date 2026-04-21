from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    unique_key: str = Field(
        sa_column=Column(String(80), unique=True, nullable=False, index=True)
    )
    profile_slug: str = Field(index=True)
    profile_label: str
    search_term: str
    source_site: str = Field(index=True)
    title: str = Field(index=True)
    company: str = Field(index=True)
    location_text: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    job_url: str = ""
    company_url: str = ""
    interval: str = ""
    currency: str = ""
    min_amount: float | None = Field(default=None, sa_column=Column(Float))
    max_amount: float | None = Field(default=None, sa_column=Column(Float))
    is_remote: bool = False
    score: float = Field(default=0.0, sa_column=Column(Float, index=True))
    title_similarity: float = Field(default=0.0, sa_column=Column(Float))
    keyword_coverage: float = Field(default=0.0, sa_column=Column(Float))
    domain_similarity: float = Field(default=0.0, sa_column=Column(Float))
    market_alignment: float = Field(default=0.0, sa_column=Column(Float))
    penalty_applied: float = Field(default=0.0, sa_column=Column(Float))
    matched_keywords: str = Field(default="", sa_column=Column(Text))
    missing_keywords: str = Field(default="", sa_column=Column(Text))
    explanation: str = Field(default="", sa_column=Column(Text))
    description: str = Field(default="", sa_column=Column(Text))
    date_posted: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    applied_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
    dismissed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
    first_seen_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True))
    )
    last_seen_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    last_refreshed_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )


class RefreshRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    profile_slug: str = Field(index=True)
    profile_label: str
    started_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    success: bool = True
    jobs_seen: int = 0
    jobs_saved: int = 0
    warnings_text: str = Field(default="", sa_column=Column(Text))
    result_json: str = Field(default="", sa_column=Column(Text))


class ExcludedCompany(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    display_name: str = Field(default="", index=True)
    normalized_name: str = Field(
        default="",
        sa_column=Column(String(255), unique=True, nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )


class TailorRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    profile_slug: str = Field(default="", index=True)
    workspace_dir: str = ""
    base_resume_path: str = ""
    session_id: str = Field(default="", index=True)
    status: str = Field(default="pending", index=True)
    current_step_key: str = Field(default="", index=True)
    current_pid: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    request_payload: str = Field(default="", sa_column=Column(Text))
    result_json: str = Field(default="", sa_column=Column(Text))
    last_message: str = Field(default="", sa_column=Column(Text))
    error_text: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class TailorRunStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    step_key: str = Field(index=True)
    session_id: str = Field(default="", index=True)
    status: str = Field(default="pending", index=True)
    prompt_path: str = ""
    last_message_path: str = ""
    log_path: str = ""
    error_text: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ApplicationTrack(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = Field(default=None, index=True)
    source_kind: str = Field(default="linked", index=True)
    title: str = Field(default="", index=True)
    company: str = Field(default="", index=True)
    source_site: str = ""
    profile_slug: str = Field(default="", index=True)
    profile_label: str = ""
    job_url: str = ""
    notes: str = Field(default="", sa_column=Column(Text))
    current_stage: str = Field(default="submitted", index=True)
    current_stage_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
    latest_notes: str = Field(default="", sa_column=Column(Text))
    applied_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )


class ApplicationTrackEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    track_id: int = Field(index=True)
    stage: str = Field(index=True)
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    notes: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), index=True),
    )

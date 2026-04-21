from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from sqlmodel import Session, delete, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import load_settings
from app.models import (
    ApplicationTrack,
    ApplicationTrackEvent,
    ExcludedCompany,
    JobRecord,
    RefreshRun,
    TailorRun,
    TailorRunStep,
)
from app.storage import JobRepository, normalize_company_name


def _sqlite_file_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return None
    return Path(database_url.removeprefix("sqlite:///"))


def _wipe_database(repository: JobRepository) -> None:
    # 中文注释：演示脚本需要可重复运行，直接清空演示相关表，保证截图和 README 一致。
    with Session(repository.engine) as session:
        for model in (
            ApplicationTrackEvent,
            ApplicationTrack,
            TailorRunStep,
            TailorRun,
            RefreshRun,
            ExcludedCompany,
            JobRecord,
        ):
            session.exec(delete(model))
        session.commit()


def _demo_jobs() -> list[JobRecord]:
    now = datetime(2026, 4, 20, 20, 0, tzinfo=timezone.utc)
    return [
        JobRecord(
            unique_key="demo-growth-orbitstack",
            profile_slug="growth-marketing",
            profile_label="Growth Marketing + Demand Gen",
            search_term='"growth marketing manager" saas',
            source_site="linkedin",
            title="Growth Marketing Manager",
            company="OrbitStack",
            location_text="Chicago, IL",
            city="Chicago",
            state="IL",
            country="USA",
            job_url="https://example.com/jobs/demo-growth-orbitstack",
            description=(
                "Own growth marketing, paid acquisition, webinar funnels, lifecycle automation, "
                "HubSpot, Salesforce, and pipeline reporting for a B2B SaaS product."
            ),
            score=91.0,
            matched_keywords="growth marketing, lifecycle marketing, HubSpot, Salesforce, pipeline",
            first_seen_at=now - timedelta(days=2),
            last_seen_at=now - timedelta(hours=1),
            last_refreshed_at=now - timedelta(hours=1),
            date_posted=now - timedelta(days=1),
        ),
        JobRecord(
            unique_key="demo-demand-helio-crm",
            profile_slug="growth-marketing",
            profile_label="Growth Marketing + Demand Gen",
            search_term='"demand generation manager"',
            source_site="indeed",
            title="Demand Generation Manager",
            company="Helio CRM",
            location_text="Austin, TX",
            city="Austin",
            state="TX",
            country="USA",
            job_url="https://example.com/jobs/demo-demand-helio-crm",
            description=(
                "Lead integrated demand generation programs across paid search, webinars, "
                "content syndication, and lifecycle nurture for SMB and mid-market pipeline."
            ),
            score=87.0,
            matched_keywords="demand generation, webinars, pipeline, lifecycle marketing",
            first_seen_at=now - timedelta(days=3),
            last_seen_at=now - timedelta(hours=3),
            last_refreshed_at=now - timedelta(hours=3),
            date_posted=now - timedelta(days=2),
        ),
        JobRecord(
            unique_key="demo-csm-northbridge",
            profile_slug="customer-success",
            profile_label="Customer Success + Expansion",
            search_term='"customer success manager" saas',
            source_site="linkedin",
            title="Customer Success Manager",
            company="Northbridge SaaS",
            location_text="Remote",
            city="",
            state="",
            country="USA",
            job_url="https://example.com/jobs/demo-csm-northbridge",
            description=(
                "Own onboarding, customer health, QBRs, renewals, and expansion planning "
                "for a mid-market SaaS book of business."
            ),
            score=89.0,
            matched_keywords="customer success, onboarding, renewals, expansion",
            applied_at=now - timedelta(days=1, hours=2),
            first_seen_at=now - timedelta(days=5),
            last_seen_at=now - timedelta(hours=5),
            last_refreshed_at=now - timedelta(hours=5),
            date_posted=now - timedelta(days=4),
        ),
        JobRecord(
            unique_key="demo-sr-csm-signalloop",
            profile_slug="customer-success",
            profile_label="Customer Success + Expansion",
            search_term='"senior customer success manager"',
            source_site="indeed",
            title="Senior Customer Success Manager",
            company="SignalLoop",
            location_text="New York, NY",
            city="New York",
            state="NY",
            country="USA",
            job_url="https://example.com/jobs/demo-sr-csm-signalloop",
            description=(
                "Lead enterprise renewals, adoption planning, executive business reviews, "
                "and customer references for strategic accounts."
            ),
            score=82.0,
            matched_keywords="customer success, renewals, QBRs, references",
            dismissed_at=now - timedelta(hours=12),
            first_seen_at=now - timedelta(days=6),
            last_seen_at=now - timedelta(hours=6),
            last_refreshed_at=now - timedelta(hours=6),
            date_posted=now - timedelta(days=5),
        ),
        JobRecord(
            unique_key="demo-ae-pipelineos",
            profile_slug="sales-growth",
            profile_label="Sales + Account Growth",
            search_term='"account executive" saas',
            source_site="linkedin",
            title="Account Executive",
            company="PipelineOS",
            location_text="Remote",
            city="",
            state="",
            country="USA",
            job_url="https://example.com/jobs/demo-ae-pipelineos",
            description=(
                "Run outbound and inbound pipeline, manage SaaS sales cycles, coordinate demos, "
                "and partner with marketing on case-study driven campaigns."
            ),
            score=80.0,
            matched_keywords="account executive, pipeline, case studies",
            first_seen_at=now - timedelta(days=2),
            last_seen_at=now - timedelta(hours=8),
            last_refreshed_at=now - timedelta(hours=8),
            date_posted=now - timedelta(days=1, hours=6),
        ),
        JobRecord(
            unique_key="demo-support-helplane",
            profile_slug="support-ops",
            profile_label="Customer Support + CX Ops",
            search_term='"support operations manager"',
            source_site="zip_recruiter",
            title="Support Operations Manager",
            company="HelpLane",
            location_text="Chicago, IL",
            city="Chicago",
            state="IL",
            country="USA",
            job_url="https://example.com/jobs/demo-support-helplane",
            description=(
                "Own support operations, workflow automation, help-center strategy, escalation routing, "
                "and SLA reporting."
            ),
            score=76.0,
            matched_keywords="support operations, workflow automation, SLA reporting",
            first_seen_at=now - timedelta(days=4),
            last_seen_at=now - timedelta(hours=7),
            last_refreshed_at=now - timedelta(hours=7),
            date_posted=now - timedelta(days=3),
        ),
        JobRecord(
            unique_key="demo-implementation-cleardesk",
            profile_slug="support-ops",
            profile_label="Customer Support + CX Ops",
            search_term='"implementation manager" saas',
            source_site="indeed",
            title="Implementation Manager",
            company="ClearDesk",
            location_text="Remote",
            city="",
            state="",
            country="USA",
            job_url="https://example.com/jobs/demo-implementation-cleardesk",
            description=(
                "Lead onboarding, customer handoff, implementation timelines, and stakeholder communication "
                "for new SaaS customers."
            ),
            score=74.0,
            matched_keywords="implementation, onboarding, stakeholder communication",
            applied_at=now - timedelta(days=2, hours=6),
            first_seen_at=now - timedelta(days=4),
            last_seen_at=now - timedelta(hours=10),
            last_refreshed_at=now - timedelta(hours=10),
            date_posted=now - timedelta(days=3, hours=4),
        ),
        JobRecord(
            unique_key="demo-cx-servicepilot",
            profile_slug="support-ops",
            profile_label="Customer Support + CX Ops",
            search_term='"customer experience manager" b2b',
            source_site="linkedin",
            title="Customer Experience Manager",
            company="ServicePilot",
            location_text="San Francisco, CA",
            city="San Francisco",
            state="CA",
            country="USA",
            job_url="https://example.com/jobs/demo-cx-servicepilot",
            description=(
                "Build customer experience programs, feedback loops, escalation policies, "
                "and operational dashboards."
            ),
            score=70.0,
            matched_keywords="customer experience, operational dashboards",
            dismissed_at=now - timedelta(days=1, hours=3),
            first_seen_at=now - timedelta(days=7),
            last_seen_at=now - timedelta(hours=9),
            last_refreshed_at=now - timedelta(hours=9),
            date_posted=now - timedelta(days=6),
        ),
    ]


def _demo_refresh_runs() -> list[RefreshRun]:
    return [
        RefreshRun(
            profile_slug="growth-marketing",
            profile_label="Growth Marketing + Demand Gen",
            started_at=datetime(2026, 4, 20, 15, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 4, 20, 15, 6, tzinfo=timezone.utc),
            success=True,
            jobs_seen=48,
            jobs_saved=12,
            warnings_text="",
            result_json=json.dumps(
                {
                    "requested_sites": ["linkedin", "indeed", "zip_recruiter"],
                    "warnings": [],
                    "query_details": [
                        {
                            "search_term": '"growth marketing manager" saas',
                            "location": "United States",
                            "requested_sites": ["linkedin", "indeed"],
                            "sites_seen": ["linkedin", "indeed"],
                            "row_count": 26,
                            "status": "success",
                            "error": "",
                        },
                        {
                            "search_term": '"demand generation manager"',
                            "location": "United States",
                            "requested_sites": ["linkedin", "indeed", "zip_recruiter"],
                            "sites_seen": ["linkedin", "zip_recruiter"],
                            "row_count": 22,
                            "status": "success",
                            "error": "",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
        ),
        RefreshRun(
            profile_slug="customer-success",
            profile_label="Customer Success + Expansion",
            started_at=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 4, 20, 9, 5, tzinfo=timezone.utc),
            success=True,
            jobs_seen=31,
            jobs_saved=9,
            warnings_text="",
            result_json=json.dumps(
                {
                    "requested_sites": ["linkedin", "indeed"],
                    "warnings": [],
                    "query_details": [
                        {
                            "search_term": '"customer success manager" saas',
                            "location": "United States",
                            "requested_sites": ["linkedin", "indeed"],
                            "sites_seen": ["linkedin", "indeed"],
                            "row_count": 18,
                            "status": "success",
                            "error": "",
                        },
                        {
                            "search_term": '"senior customer success manager"',
                            "location": "United States",
                            "requested_sites": ["linkedin", "indeed"],
                            "sites_seen": ["linkedin"],
                            "row_count": 13,
                            "status": "success",
                            "error": "",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
        ),
        RefreshRun(
            profile_slug="support-ops",
            profile_label="Customer Support + CX Ops",
            started_at=datetime(2026, 4, 19, 22, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 4, 19, 22, 4, tzinfo=timezone.utc),
            success=False,
            jobs_seen=14,
            jobs_saved=3,
            warnings_text="429 from linkedin",
            result_json=json.dumps(
                {
                    "requested_sites": ["linkedin", "indeed"],
                    "warnings": ["429 from linkedin"],
                    "query_details": [
                        {
                            "search_term": '"customer support manager"',
                            "location": "United States",
                            "requested_sites": ["linkedin", "indeed"],
                            "sites_seen": ["indeed"],
                            "row_count": 14,
                            "status": "error",
                            "error": "429 from linkedin",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed reproducible QuickApply demo data.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Clear the configured database before inserting demo data.",
    )
    args = parser.parse_args()

    settings = load_settings()
    database_path = _sqlite_file_path(settings.app.database_url)
    if args.replace and database_path and database_path.exists():
        database_path.unlink()

    repository = JobRepository(settings.app.database_url)
    repository.init_db()

    if args.replace:
        _wipe_database(repository)

    jobs = _demo_jobs()
    repository.upsert_jobs(jobs)

    # 中文注释：重新读取一次，确保拿到数据库主键，后续才能绑定 track。
    with Session(repository.engine) as session:
        persisted_job_ids = {
            job.unique_key: job.id or 0
            for job in session.exec(select(JobRecord)).all()
        }
        session.exec(delete(ExcludedCompany))
        session.commit()

    for run in _demo_refresh_runs():
        repository.record_refresh_run(run)

    repository.create_excluded_company("OutsourcedCallers LLC")
    repository.create_excluded_company("Growth Loop Agency")

    northbridge_job_id = persisted_job_ids["demo-csm-northbridge"]
    cleardesk_job_id = persisted_job_ids["demo-implementation-cleardesk"]

    northbridge_track = repository.sync_application_track_for_job(
        northbridge_job_id,
        applied_at=datetime(2026, 4, 19, 18, 0, tzinfo=timezone.utc),
    )
    cleardesk_track = repository.sync_application_track_for_job(
        cleardesk_job_id,
        applied_at=datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc),
    )

    if northbridge_track is not None:
        repository.add_application_track_event(
            northbridge_track.id or 0,
            stage="introduced",
            occurred_at=datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc),
            notes="Referral intro completed and QBR examples requested.",
        )
        repository.add_application_track_event(
            northbridge_track.id or 0,
            stage="interviewed",
            occurred_at=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
            notes="Phone screen booked for next week.",
        )

    if cleardesk_track is not None:
        repository.add_application_track_event(
            cleardesk_track.id or 0,
            stage="introduced",
            occurred_at=datetime(2026, 4, 19, 19, 0, tzinfo=timezone.utc),
            notes="Hiring manager asked for onboarding case study.",
        )

    repository.create_manual_application_track(
        ApplicationTrack(
            source_kind="manual",
            title="Strategic Account Manager",
            company="Referral Hub",
            source_site="referral",
            profile_slug="sales-growth",
            profile_label="Sales + Account Growth",
            job_url="https://example.com/jobs/manual-referral-hub",
            notes="Warm intro from former customer. Emphasize reference program and expansion playbooks.",
            current_stage="submitted",
            current_stage_at=datetime(2026, 4, 18, 18, 30, tzinfo=timezone.utc),
            applied_at=datetime(2026, 4, 18, 18, 30, tzinfo=timezone.utc),
        )
    )

    if database_path:
        print(f"Seeded QuickApply demo data into {database_path}")
    else:
        print("Seeded QuickApply demo data.")


if __name__ == "__main__":
    main()

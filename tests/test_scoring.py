from datetime import datetime, timezone

from app.config import SearchProfileConfig, load_settings
from app.fetcher import FetchedJob
from app.resume_profile import build_resume_profile
from app.scoring import (
    DOMAIN_WEIGHT,
    KEYWORD_WEIGHT,
    MARKET_WEIGHT,
    STOP_KEYWORD_PENALTY,
    TITLE_WEIGHT,
    score_job,
)
from app.time_utils import format_local_time


def test_resume_profile_loads_resume_sources() -> None:
    settings = load_settings()
    profile = build_resume_profile(settings.resume_profile)

    assert profile.source_files
    assert len(profile.source_files) >= 4
    assert any(path.endswith("taylor_brooks_general.tex") for path in profile.source_files)
    assert any(path.endswith("taylor_brooks_growth_marketing.tex") for path in profile.source_files)
    assert "customer success" in profile.resume_text.lower()


def test_score_job_prefers_targeted_growth_role() -> None:
    settings = load_settings()
    profile = build_resume_profile(settings.resume_profile)

    good_job = FetchedJob(
        unique_key="good",
        search_term='"growth marketing manager" saas',
        source_site="indeed",
        title="Growth Marketing Manager",
        company="Example Labs",
        location_text="Remote",
        city="",
        state="",
        country="USA",
        job_url="https://example.com/jobs/1",
        company_url="",
        interval="yearly",
        currency="USD",
        min_amount=150000.0,
        max_amount=180000.0,
        is_remote=True,
        description=(
            "Own growth marketing, demand generation, lifecycle automation, "
            "HubSpot, Salesforce, conversion reporting, and pipeline generation."
        ),
        date_posted=None,
    )
    bad_job = FetchedJob(
        unique_key="bad",
        search_term='"growth marketing manager" saas',
        source_site="indeed",
        title="Research Scientist",
        company="Example Labs",
        location_text="Remote",
        city="",
        state="",
        country="USA",
        job_url="https://example.com/jobs/2",
        company_url="",
        interval="yearly",
        currency="USD",
        min_amount=120000.0,
        max_amount=140000.0,
        is_remote=True,
        description="Run molecular simulation workflows, protein modeling, and wet-lab assay analysis.",
        date_posted=None,
    )

    good_score = score_job(good_job, profile)
    bad_score = score_job(bad_job, profile)

    assert good_score.total_score > 60
    assert bad_score.total_score < good_score.total_score


def test_scoring_formula_weights_are_stable() -> None:
    assert TITLE_WEIGHT == 0.45
    assert KEYWORD_WEIGHT == 0.30
    assert DOMAIN_WEIGHT == 0.15
    assert MARKET_WEIGHT == 0.10
    assert STOP_KEYWORD_PENALTY == 0.18
    assert round(TITLE_WEIGHT + KEYWORD_WEIGHT + DOMAIN_WEIGHT + MARKET_WEIGHT, 2) == 1.00


def test_score_job_respects_market_supply_hint() -> None:
    settings = load_settings()
    profile = build_resume_profile(settings.resume_profile)
    job = FetchedJob(
        unique_key="market-hint",
        search_term='"customer success manager" saas',
        source_site="linkedin",
        title="Customer Success Manager",
        company="Example Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/market-hint",
        company_url="",
        interval="yearly",
        currency="USD",
        min_amount=150000.0,
        max_amount=180000.0,
        is_remote=False,
        description="Customer onboarding, renewals, success plans, expansion, QBRs, and customer health reviews.",
        date_posted=None,
    )
    high_supply = SearchProfileConfig(
        slug="customer-success",
        label="Customer Success + Expansion",
        search_terms=['"customer success manager" saas'],
        search_term_weights={'"customer success manager" saas': 1.0},
        market_priority=0.92,
    )
    low_supply = SearchProfileConfig(
        slug="support-ops",
        label="Customer Support + CX Ops",
        search_terms=['"customer success manager" saas'],
        search_term_weights={'"customer success manager" saas': 0.45},
        market_priority=0.45,
    )

    high_supply_score = score_job(job, profile, high_supply)
    low_supply_score = score_job(job, profile, low_supply)

    assert high_supply_score.market_alignment > low_supply_score.market_alignment
    assert high_supply_score.total_score > low_supply_score.total_score


def test_format_local_time_uses_chicago_timezone() -> None:
    assert (
        format_local_time(
            datetime(2026, 4, 13, 17, 10, tzinfo=timezone.utc),
            "%Y-%m-%d %H:%M %Z",
        )
        == "2026-04-13 12:10 CDT"
    )


def test_format_local_time_accepts_iso_string() -> None:
    assert (
        format_local_time(
            "2026-04-13T23:08:06+00:00",
            "%Y-%m-%d %H:%M %Z",
        )
        == "2026-04-13 18:08 CDT"
    )

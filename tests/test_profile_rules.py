from __future__ import annotations

from app.config import SearchProfileConfig
from app.fetcher import FetchedJob, _as_text
from app.profile_rules import build_fetched_job_rule_blob, matches_search_profile_rules


def _job(description: str, search_term: str = '"data scientist" pharmaceutical') -> FetchedJob:
    return FetchedJob(
        unique_key="k",
        search_term=search_term,
        source_site="indeed",
        title="Data Scientist",
        company="Example Co",
        location_text="Boston, MA",
        city="",
        state="",
        country="USA",
        job_url="https://example.com/jobs/1",
        company_url="",
        interval="",
        currency="",
        min_amount=None,
        max_amount=None,
        is_remote=False,
        description=description,
        date_posted=None,
    )


PROFILE = SearchProfileConfig(slug="ds", label="DS", require_any_keywords=["pharma"])


def test_search_term_does_not_satisfy_require_keywords_when_description_exists() -> None:
    # 中文注释：有真实描述时，search_term 里的 "pharmaceutical" 不应让 require 自动通过。
    job = _job("Build ad ranking models for an e-commerce marketplace.")
    assert not matches_search_profile_rules(build_fetched_job_rule_blob(job), PROFILE)


def test_search_term_is_fallback_evidence_when_description_missing() -> None:
    for missing in ("", "nan"):
        job = _job(missing)
        assert matches_search_profile_rules(build_fetched_job_rule_blob(job), PROFILE)


def test_as_text_drops_pandas_missing_values() -> None:
    assert _as_text(float("nan")) == ""
    assert _as_text("nan") == ""
    assert _as_text(None) == ""
    assert _as_text("  Data Scientist ") == "Data Scientist"

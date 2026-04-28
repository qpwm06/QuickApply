from __future__ import annotations

import subprocess

import pytest

from app.config import SearchProfileConfig
from app.fetcher import JobSpyFetcher


def _make_profile() -> SearchProfileConfig:
    return SearchProfileConfig(
        slug="retry-test",
        label="Retry Test",
        search_terms=["sci ml"],
        locations=["Remote"],
        sites=["linkedin"],
        results_wanted=10,
        hours_old=72,
        country_indeed="USA",
    )


def _make_fetcher() -> JobSpyFetcher:
    fetcher = JobSpyFetcher.__new__(JobSpyFetcher)
    fetcher.timeout_seconds = 30
    fetcher.proxy_urls = []
    return fetcher


def test_run_query_retries_on_timeout(monkeypatch) -> None:
    fetcher = _make_fetcher()
    calls = {"count": 0}

    def fake_invoke(_self, profile, search_term, location):
        calls["count"] += 1
        if calls["count"] < 3:
            raise subprocess.TimeoutExpired(cmd="python", timeout=1)
        return [{"site": "linkedin", "title": "x"}]

    monkeypatch.setattr(JobSpyFetcher, "_invoke_jobspy", fake_invoke)
    monkeypatch.setattr("app.fetcher.time.sleep", lambda _seconds: None)

    rows, retry_count, retry_errors = fetcher._run_query(_make_profile(), "sci ml", "Remote")

    assert rows == [{"site": "linkedin", "title": "x"}]
    assert retry_count == 2
    assert len(retry_errors) == 2


def test_run_query_does_not_retry_for_non_retryable_errors(monkeypatch) -> None:
    fetcher = _make_fetcher()
    calls = {"count": 0}

    def fake_invoke(_self, profile, search_term, location):
        calls["count"] += 1
        raise RuntimeError("authentication failed")

    monkeypatch.setattr(JobSpyFetcher, "_invoke_jobspy", fake_invoke)
    monkeypatch.setattr("app.fetcher.time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="authentication failed"):
        fetcher._run_query(_make_profile(), "sci ml", "Remote")
    assert calls["count"] == 1


def test_run_query_gives_up_after_max_retries(monkeypatch) -> None:
    fetcher = _make_fetcher()
    calls = {"count": 0}

    def fake_invoke(_self, profile, search_term, location):
        calls["count"] += 1
        raise RuntimeError("connection refused")

    monkeypatch.setattr(JobSpyFetcher, "_invoke_jobspy", fake_invoke)
    monkeypatch.setattr("app.fetcher.time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="connection refused"):
        fetcher._run_query(_make_profile(), "sci ml", "Remote")
    assert calls["count"] == 1 + len(JobSpyFetcher._RETRY_DELAYS_SECONDS)

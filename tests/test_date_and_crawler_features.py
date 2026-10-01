from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timezone

from sqlmodel import Session, select

import app.config as config_module
from app.config import SearchProfileConfig
from app.fetcher import JobSpyFetcher, _summarize_stderr
from app.models import JobRecord, RefreshRun
from app.storage import _shift_months
from app.time_utils import normalize_date_range
from tests.test_routes import _write_test_config


def _make_app(tmp_path, monkeypatch):
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    import app.main as main_module

    main_module = importlib.reload(main_module)
    return main_module.create_app()


def _job(key: str, title: str, *, first_seen: datetime, posted: datetime | None) -> JobRecord:
    return JobRecord(
        unique_key=key,
        profile_slug="scientific-ml",
        profile_label="Scientific ML",
        search_term='"scientific machine learning"',
        source_site="linkedin",
        title=title,
        company=f"{title} Labs",
        location_text="Cambridge, MA",
        city="",
        state="",
        country="",
        job_url=f"https://example.com/jobs/{key}",
        description="Build scientific machine learning workflows for molecules.",
        score=50.0,
        first_seen_at=first_seen,
        last_refreshed_at=first_seen,
        date_posted=posted,
    )


def _seed_jobs(repository) -> None:
    repository.upsert_jobs(
        [
            _job(
                "early",
                "Early Scientist",
                first_seen=datetime(2026, 9, 1, 15, tzinfo=timezone.utc),
                posted=datetime(2026, 8, 30),
            ),
            _job(
                "late",
                "Late Scientist",
                first_seen=datetime(2026, 9, 20, 15, tzinfo=timezone.utc),
                posted=datetime(2026, 9, 19),
            ),
        ]
    )
    # 中文注释：upsert 会自己写 first_seen_at，这里强制回填测试用时间。
    with Session(repository.engine) as session:
        for key, seen in (
            ("early", datetime(2026, 9, 1, 15, tzinfo=timezone.utc)),
            ("late", datetime(2026, 9, 20, 15, tzinfo=timezone.utc)),
        ):
            job = session.exec(select(JobRecord).where(JobRecord.unique_key == key)).one()
            job.first_seen_at = seen
            session.add(job)
        session.commit()


# ---------- 1. 追踪图：当季 / 近半年 / 指定日期 ----------


def test_shift_months_and_date_range_helpers() -> None:
    assert _shift_months(date(2026, 8, 31), -6) == date(2026, 2, 28)
    assert _shift_months(date(2026, 3, 15), -6) == date(2025, 9, 15)
    assert normalize_date_range(date(2026, 9, 30), date(2026, 9, 1)) == (date(2026, 9, 1), date(2026, 9, 30))
    assert normalize_date_range(date(2026, 9, 1), None) == (date(2026, 9, 1), None)


def test_tracker_chart_supports_quarter_half_year_and_custom(tmp_path, monkeypatch) -> None:
    web_app = _make_app(tmp_path, monkeypatch)
    repository = web_app.config["repository"]
    reference = datetime(2026, 10, 1, 18, tzinfo=timezone.utc)

    quarter = repository.application_track_daily_counts(range_key="quarter", reference_time=reference)
    assert quarter["labels"][0] == "2026-10-01"
    assert quarter["labels"][-1] == "2026-10-01"

    half_year = repository.application_track_daily_counts(range_key="half_year", reference_time=reference)
    assert half_year["labels"][0] == "2026-04-02"
    assert half_year["labels"][-1] == "2026-10-01"

    custom = repository.application_track_daily_counts(
        range_key="custom",
        reference_time=reference,
        custom_start=date(2026, 9, 10),
        custom_end=date(2026, 9, 12),
    )
    assert custom["labels"] == ["2026-09-10", "2026-09-11", "2026-09-12"]

    only_start = repository.application_track_daily_counts(
        range_key="custom",
        reference_time=reference,
        custom_start=date(2026, 9, 28),
    )
    assert only_start["labels"] == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]


def test_tracker_page_renders_new_ranges_and_custom_dates(tmp_path, monkeypatch) -> None:
    web_app = _make_app(tmp_path, monkeypatch)
    client = web_app.test_client()

    html = client.get("/application-tracker").get_data(as_text=True)
    assert "当季" in html
    assert "近半年" in html
    assert 'name="chart_start"' in html

    custom_html = client.get("/application-tracker?chart_start=2026-09-01&chart_end=2026-09-05").get_data(as_text=True)
    assert 'value="2026-09-01"' in custom_html
    assert 'data-tracker-chart-range="custom"' in custom_html or 'data-tracker-chart-range="all"' in custom_html


# ---------- 2. 职位：日期范围筛选 + 批量不合适 ----------


def test_jobs_date_filter_supports_single_sided_ranges(tmp_path, monkeypatch) -> None:
    web_app = _make_app(tmp_path, monkeypatch)
    repository = web_app.config["repository"]
    _seed_jobs(repository)

    after = repository.list_jobs(date_from=date(2026, 9, 10))
    before = repository.list_jobs(date_to=date(2026, 9, 10))
    both = repository.list_jobs(date_from=date(2026, 9, 1), date_to=date(2026, 9, 1))
    posted = repository.list_jobs(date_field="posted", date_to=date(2026, 8, 30))

    assert [job.title for job in after] == ["Late Scientist"]
    assert [job.title for job in before] == ["Early Scientist"]
    assert [job.title for job in both] == ["Early Scientist"]
    # 中文注释：发布日期按“纯日期”比较，2026-08-30 当天发布的要包含在“截止 8/30”里。
    assert [job.title for job in posted] == ["Early Scientist"]

    client = web_app.test_client()
    html = client.get("/jobs?date_from=2026-09-10").get_data(as_text=True)
    assert "Late Scientist" in html
    assert "Early Scientist" not in html
    assert 'value="2026-09-10"' in html
    # 中文注释：发布日期展示不能因为时区转换早一天。
    assert "发布 2026-09-19" in html


def test_bulk_dismiss_marks_selected_jobs_and_skips_applied(tmp_path, monkeypatch) -> None:
    web_app = _make_app(tmp_path, monkeypatch)
    repository = web_app.config["repository"]
    _seed_jobs(repository)
    with Session(repository.engine) as session:
        early = session.exec(select(JobRecord).where(JobRecord.unique_key == "early")).one()
        late = session.exec(select(JobRecord).where(JobRecord.unique_key == "late")).one()
        early_id, late_id = int(early.id), int(late.id)
    repository.sync_application_track_for_job(late_id, applied_at=datetime.now(timezone.utc))

    client = web_app.test_client()
    response = client.post(
        "/jobs/dismiss-bulk",
        data={"job_ids": [str(early_id), str(late_id)], "return_to": "/jobs"},
        headers={"Accept": "application/json", "X-Requested-With": "resume-job-monitor"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["job_ids"] == [early_id]
    assert repository.get_job(early_id).dismissed_at is not None
    assert repository.get_job(late_id).dismissed_at is None

    empty = client.post(
        "/jobs/dismiss-bulk",
        data={"return_to": "/jobs"},
        headers={"Accept": "application/json", "X-Requested-With": "resume-job-monitor"},
    )
    assert empty.status_code == 400


# ---------- 3. 抓取记录：按日期删除 + 状态判定 ----------


def _record_run(repository, started_at: datetime, *, statuses: list[str], warnings: list[str]) -> None:
    repository.record_refresh_run(
        RefreshRun(
            profile_slug="scientific-ml",
            profile_label="Scientific ML",
            success=False,
            jobs_seen=3,
            jobs_saved=1,
            warnings_text="\n".join(warnings),
            result_json=json.dumps(
                {
                    "warnings": warnings,
                    "requested_sites": ["linkedin"],
                    "query_details": [
                        {"search_term": f"q{index}", "location": "US", "status": status, "row_count": 1}
                        for index, status in enumerate(statuses)
                    ],
                }
            ),
            started_at=started_at,
            finished_at=started_at,
        )
    )


def test_crawler_status_labels_and_delete_by_date(tmp_path, monkeypatch) -> None:
    web_app = _make_app(tmp_path, monkeypatch)
    repository = web_app.config["repository"]
    # 中文注释：老记录“重试后成功”被存成 success=False，展示时应识别为成功（有警告）。
    _record_run(
        repository,
        datetime(2026, 8, 14, 15, tzinfo=timezone.utc),
        statuses=["ok", "ok"],
        warnings=["q0 succeeded after 1 retry"],
    )
    _record_run(repository, datetime(2026, 8, 15, 15, tzinfo=timezone.utc), statuses=["ok", "error"], warnings=["boom"])
    _record_run(repository, datetime(2026, 9, 1, 15, tzinfo=timezone.utc), statuses=["error"], warnings=["boom"])

    client = web_app.test_client()
    html = client.get("/crawler?runs_limit=30").get_data(as_text=True)
    assert "成功（有警告）" in html
    assert "部分失败 1/2" in html
    assert "共 3 条抓取记录" in html

    refused = client.post("/crawler/runs/delete", data={}, follow_redirects=True).get_data(as_text=True)
    assert "请至少选择一个日期" in refused
    assert repository.count_refresh_runs() == 3

    deleted = client.post(
        "/crawler/runs/delete",
        data={"run_date_to": "2026-08-15"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "已删除 2026-08-15 及以前的 2 条抓取记录" in deleted
    assert repository.count_refresh_runs() == 1


# ---------- 3b. 抓取器：站点隔离 / 断网快速失败 ----------


def _fetcher() -> JobSpyFetcher:
    fetcher = JobSpyFetcher.__new__(JobSpyFetcher)
    fetcher.timeout_seconds = 30
    fetcher.proxy_urls = []
    return fetcher


def _profile(sites: list[str], terms: list[str]) -> SearchProfileConfig:
    return SearchProfileConfig(
        slug="iso",
        label="Iso",
        search_terms=terms,
        locations=["United States"],
        sites=sites,
    )


def test_partial_site_failure_keeps_other_site_rows(monkeypatch) -> None:
    def fake_invoke(_self, profile, search_term, location):
        return {
            "rows": [{"site": "linkedin", "title": "ML Scientist", "company": "Co"}],
            "site_errors": {"indeed": "SSLError: EOF occurred"},
        }

    monkeypatch.setattr(JobSpyFetcher, "_invoke_jobspy", fake_invoke)
    jobs, warnings, details = _fetcher().fetch_profile(_profile(["linkedin", "indeed"], ["q"]))

    assert [job.title for job in jobs] == ["ML Scientist"]
    assert details[0]["status"] == "partial"
    assert details[0]["site_errors"] == {"indeed": "SSLError: EOF occurred"}
    assert any("site=indeed failed" in warning for warning in warnings)


def test_all_sites_failing_is_retried_then_network_down_skips_rest(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_invoke(_self, profile, search_term, location):
        calls["count"] += 1
        return {"rows": [], "site_errors": {"linkedin": "ConnectionError: Max retries exceeded"}}

    monkeypatch.setattr(JobSpyFetcher, "_invoke_jobspy", fake_invoke)
    monkeypatch.setattr("app.fetcher.time.sleep", lambda _seconds: None)
    _jobs, warnings, details = _fetcher().fetch_profile(_profile(["linkedin"], ["q1", "q2", "q3", "q4"]))

    attempts_per_query = 1 + len(JobSpyFetcher._RETRY_DELAYS_SECONDS)
    assert calls["count"] == JobSpyFetcher._NETWORK_FAILURE_LIMIT * attempts_per_query
    assert [detail["status"] for detail in details] == ["error", "error", "skipped", "skipped"]
    assert any("skipped the remaining queries" in warning for warning in warnings)


def test_summarize_stderr_keeps_only_last_line() -> None:
    stderr = "2026 - INFO - JobSpy:Linkedin - finished\nTraceback ...\nrequests.exceptions.SSLError: EOF\n"
    assert _summarize_stderr(stderr) == "requests.exceptions.SSLError: EOF"
    assert _summarize_stderr("") == ""

from __future__ import annotations

import importlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlmodel import Session, select

import app.config as config_module
from app.models import ApplicationTrack, JobRecord, RefreshRun, TailorRun


def _write_test_config(tmp_path: Path) -> Path:
    resume_path = tmp_path / "resume.tex"
    resume_path.write_text(
        "\\section{Experience}\nBuilt scientific machine learning workflows.\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "search_profiles.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "app": {
                    "database_url": f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}",
                    "workspaces_dir": str(tmp_path / "Role"),
                    "refresh_interval_minutes": 720,
                    "default_limit": 60,
                    "default_min_score": 0,
                    "min_score_to_store": 18,
                },
                "resume_profile": {
                    "name": "Route Test",
                    "summary": "Simulation-first scientist.",
                    "source_files": [str(resume_path)],
                    "target_titles": ["Scientific ML Scientist"],
                    "focus_domains": ["scientific machine learning"],
                    "weighted_keywords": {"scientific machine learning": 1.8},
                    "stop_keywords": ["sales"],
                },
                "search_profiles": [
                    {
                        "slug": "scientific-ml",
                        "label": "Scientific ML",
                        "enabled": True,
                        "search_terms": ['"scientific machine learning"'],
                        "locations": ["United States"],
                        "sites": ["linkedin", "indeed"],
                        "default_resume_file": str(resume_path),
                    }
                ],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return config_path


def test_dashboard_routes_render_with_admin_shell(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-test-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Scientific ML Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-test-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
                matched_keywords="scientific machine learning, molecules",
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    client = web_app.test_client()
    root_response = client.get("/")
    dashboard_response = client.get("/dashboard")
    crawler_response = client.get("/crawler")
    jobs_response = client.get("/jobs")
    tracker_response = client.get("/application-tracker")
    tailor_response = client.get("/tailor-tasks")
    detail_response = client.get(f"/jobs/{job.id}")

    assert root_response.status_code == 302
    assert root_response.location.endswith("/dashboard")
    assert dashboard_response.status_code == 200
    assert crawler_response.status_code == 200
    assert jobs_response.status_code == 200
    assert tracker_response.status_code == 200
    assert tailor_response.status_code == 200
    assert detail_response.status_code == 200

    dashboard_html = dashboard_response.get_data(as_text=True)
    crawler_html = crawler_response.get_data(as_text=True)
    jobs_html = jobs_response.get_data(as_text=True)
    tracker_html = tracker_response.get_data(as_text=True)
    tailor_html = tailor_response.get_data(as_text=True)
    detail_html = detail_response.get_data(as_text=True)

    assert "Career Ops" in dashboard_html
    assert "内容管理" in dashboard_html
    assert 'data-language-option="zh"' in dashboard_html
    assert 'data-language-option="en"' in dashboard_html
    assert 'data-i18n-text="后台待命"' in dashboard_html
    assert '/static/i18n.js' in dashboard_html
    assert "Scientific ML Scientist" in jobs_html
    assert "简历精修" in jobs_html
    assert "投递追踪页" in jobs_html
    assert 'data-i18n-placeholder="手工加入需要屏蔽的公司"' in jobs_html
    assert "新增画像" in crawler_html
    assert 'data-i18n-placeholder="可留空，自动根据名称生成"' in crawler_html
    assert "https://www.linkedin.com/jobs/search/" in crawler_html
    assert "供给" not in crawler_html
    assert "市场层级" not in crawler_html
    assert "画像供给权重" not in crawler_html
    assert "打分公式：" not in crawler_html
    assert 'data-tracker-chart' in tracker_html
    assert 'data-i18n-placeholder="LinkedIn / Indeed / 内推公司"' in tracker_html
    assert 'data-i18n-placeholder="职位或公司"' in tracker_html
    assert "默认折叠" in detail_html
    assert "一键生成" in detail_html
    assert "重新生成修改建议" in detail_html
    assert "Tailor Workspace" in detail_html
    assert "Workspace Summary" in detail_html
    assert "markdown-preview" in detail_html
    assert "resume_revision_advice.md" in detail_html
    assert "session_instruction.md" in detail_html
    assert "Markdown Preview" in detail_html
    assert detail_html.count("查看 skill") >= 2
    assert detail_html.count("打开 skill 文件") >= 2
    assert "Session 状态" in detail_html
    assert "最近消息" in detail_html
    assert "最近 Session 日志" in detail_html
    assert "发送给 Session 的信息" in detail_html
    assert "发送建议到 Session" in detail_html
    assert "data-open-url=" in detail_html
    assert "data-browser-window-route=" in detail_html
    assert "打开 Finder 工作区" in detail_html
    assert "打开 Finder 文件" in detail_html
    assert "恢复 / 重建 Session" in detail_html
    assert "当前工作区按职位汇总" in detail_html
    assert "生成修改建议并自动建 Session" not in detail_html
    assert "打开原始 md" not in detail_html
    assert "定位文件" not in detail_html
    assert "原始岗位信息" not in detail_html
    assert "本轮修改指令" not in detail_html
    assert "Agent 查看" not in detail_html
    assert "Agent 优化" not in detail_html
    assert 'id="final-resume-text"' not in detail_html
    assert "<iframe" in detail_html
    assert "工作区 / 模板" not in tailor_html
    assert "累计运行" in tailor_html
    assert "手工新增" in tracker_html


def test_i18n_script_covers_remaining_ui_shell_fragments() -> None:
    script_path = Path(__file__).resolve().parents[1] / "static" / "i18n.js"
    script_text = script_path.read_text(encoding="utf-8")

    assert '".stat-card strong"' in script_text
    assert '".mini-surface strong"' in script_text
    assert '".muted-copy"' in script_text
    assert '".timeline-fallback-copy"' in script_text
    assert '".jobs-summary-label"' in script_text
    assert '".term-chip-launch"' in script_text
    assert "data-i18n-text" in script_text
    assert "后台待命" in script_text
    assert "translateScoringFormula" in script_text
    assert "最高 ([\\d.]+)" in script_text
    assert "最佳 ([\\d.]+)" in script_text
    assert "时间按 (.+) 解释并保存。" in script_text
    assert "打分公式：" in script_text
    assert "Application Activity Chart" in script_text
    assert "No data is available for the selected range." in script_text


def test_tailor_skill_detail_page_renders_codex_skill(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-skill-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Skill Detail Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-skill-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    client = web_app.test_client()
    response = client.get(f"/jobs/{job.id}/tailor/skills/revision_advice")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "修改建议 Skill" in html
    assert "渲染预览" in html
    assert "原始文本" in html
    assert "Selected Wins" in html
    assert "打开 Finder 文件" in html


def test_crawler_supports_location_updates_and_history_table(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.record_refresh_run(
        RefreshRun(
            profile_slug="scientific-ml",
            profile_label="Scientific ML",
            success=False,
            jobs_seen=12,
            jobs_saved=4,
            warnings_text="429 from linkedin",
            result_json=json.dumps(
                {
                    "warnings": ["429 from linkedin"],
                    "requested_sites": ["linkedin", "indeed"],
                    "query_details": [
                        {
                            "search_term": '"scientific machine learning"',
                            "location": "United States",
                            "requested_sites": ["linkedin", "indeed"],
                            "sites_seen": ["linkedin"],
                            "row_count": 12,
                            "status": "error",
                            "error": "429 from linkedin",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            started_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 4, 14, 12, 8, tzinfo=timezone.utc),
        )
    )
    run = repository.latest_refresh_runs(limit=1)[0]

    client = web_app.test_client()
    update_response = client.post(
        "/profiles/scientific-ml/locations",
        data={
            "redirect_to": "crawler",
            "locations": "United States | Chicago, IL",
        },
        follow_redirects=True,
    )
    html = update_response.get_data(as_text=True)
    detail_html = client.get(f"/crawler/runs/{run.id}").get_data(as_text=True)

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    profile_raw = next(item for item in saved["search_profiles"] if item["slug"] == "scientific-ml")

    assert update_response.status_code == 200
    assert "已更新 Scientific ML 的搜索地点。" in html
    assert "United States" in html
    assert "Chicago, IL" in html
    assert "开始时间" in html
    assert "结束时间" in html
    assert "查看详情" in html
    assert "429 from linkedin" not in html
    assert "429 from linkedin" in detail_html
    assert "按关键词和地点拆开的抓取结果" in detail_html
    assert profile_raw["locations"] == ["United States", "Chicago, IL"]


def test_repository_jobs_keyword_filters_and_counts_are_case_insensitive(
    tmp_path, monkeypatch
) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="repo-keyword-description",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Materials Scientist",
                company="Bright Lab",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/repo-keyword-description",
                description="Strong POSTDOC-facing role in materials modeling.",
                score=91.0,
            ),
            JobRecord(
                unique_key="repo-keyword-search-term",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"POSTDOC" materials chemistry',
                source_site="indeed",
                title="Research Scientist",
                company="North Materials",
                location_text="Boston, MA",
                city="Boston",
                state="MA",
                country="USA",
                job_url="https://example.com/jobs/repo-keyword-search-term",
                description="Build atomistic workflows.",
                score=88.0,
            ),
            JobRecord(
                unique_key="repo-keyword-excluded",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"postdoc" catalysts',
                source_site="linkedin",
                title="Summer INTERN",
                company="Intern Corp",
                location_text="Houston, TX",
                city="Houston",
                state="TX",
                country="USA",
                job_url="https://example.com/jobs/repo-keyword-excluded",
                description="Postdoc pipeline role.",
                score=85.0,
            ),
            JobRecord(
                unique_key="repo-keyword-applied",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"postdoc" chemistry',
                source_site="linkedin",
                title="Applied Postdoc",
                company="Applied Lab",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/repo-keyword-applied",
                description="Postdoc role in computational chemistry.",
                score=84.0,
                applied_at=datetime(2026, 4, 14, 12, 0, tzinfo=timezone.utc),
            ),
            JobRecord(
                unique_key="repo-keyword-reviewed-once",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"postdoc" polymers',
                source_site="linkedin",
                title="Reviewed Postdoc",
                company="Review Lab",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/repo-keyword-reviewed-once",
                description="Postdoc role already reviewed.",
                score=83.0,
                applied_at=datetime(2026, 4, 14, 8, 0, tzinfo=timezone.utc),
                dismissed_at=datetime(2026, 4, 14, 18, 0, tzinfo=timezone.utc),
            ),
        ]
    )

    jobs = repository.list_jobs(
        include_keywords=["postdoc"],
        exclude_keywords=["intern"],
        sort_by="score",
        limit=10,
    )
    counts = repository.jobs_filter_counts(
        include_keywords=["postdoc"],
        exclude_keywords=["intern"],
        sort_by="score",
    )

    assert [job.title for job in jobs] == [
        "Materials Scientist",
        "Research Scientist",
    ]
    assert counts == {
        "remaining_count": 2,
        "applied_count": 2,
        "reviewed_count": 2,
    }


def test_jobs_page_renders_keyword_filters_counts_and_sort_urls(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-jobs-remaining-title",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"materials chemistry"',
                source_site="linkedin",
                title="Postdoctoral Researcher",
                company="Bright Lab",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-jobs-remaining-title",
                description="Materials chemistry and simulation workflows.",
                score=92.0,
            ),
            JobRecord(
                unique_key="route-jobs-remaining-description",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="indeed",
                title="Research Scientist",
                company="North Materials",
                location_text="Boston, MA",
                city="Boston",
                state="MA",
                country="USA",
                job_url="https://example.com/jobs/route-jobs-remaining-description",
                description="Ideal postdoc transition role for atomistic modeling.",
                score=88.0,
            ),
            JobRecord(
                unique_key="route-jobs-filtered-out",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"postdoc" catalysts',
                source_site="linkedin",
                title="Research Intern",
                company="Intern Corp",
                location_text="Austin, TX",
                city="Austin",
                state="TX",
                country="USA",
                job_url="https://example.com/jobs/route-jobs-filtered-out",
                description="Postdoc pipeline role.",
                score=87.0,
            ),
            JobRecord(
                unique_key="route-jobs-applied",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"postdoc" chemistry',
                source_site="linkedin",
                title="Applied Postdoc",
                company="Applied Lab",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-jobs-applied",
                description="Computational chemistry postdoc role.",
                score=86.0,
                applied_at=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
            ),
            JobRecord(
                unique_key="route-jobs-dismissed",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"postdoc" polymers',
                source_site="linkedin",
                title="Dismissed Postdoc",
                company="No Fit Lab",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-jobs-dismissed",
                description="Polymer postdoc role.",
                score=84.0,
                dismissed_at=datetime(2026, 4, 14, 11, 0, tzinfo=timezone.utc),
            ),
        ]
    )

    client = web_app.test_client()
    response = client.get("/jobs?include_keywords=postdoc&exclude_keywords=intern&sort_by=score")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Postdoctoral Researcher" in html
    assert "Research Scientist" in html
    assert "Research Intern" not in html
    assert 'name="include_keywords" value="postdoc"' in html
    assert 'name="exclude_keywords" value="intern"' in html
    assert 'data-i18n-text="剩余">剩余</span>' in html
    assert 'data-i18n-text="已投递">已投递</span>' in html
    assert 'data-i18n-text="已查阅">已查阅</span>' in html
    assert "<strong>2</strong>" in html
    assert "<strong>1</strong>" in html
    assert "include_keywords=postdoc" in html
    assert "exclude_keywords=intern" in html
    assert 'const jobsKeywordStorageKey = "quickapply:jobs-keyword-filters";' in html
    assert "localStorage.getItem(jobsKeywordStorageKey)" in html
    assert "localStorage.setItem(jobsKeywordStorageKey, JSON.stringify(payload));" in html
    assert "currentUrlHasExplicitKeywordFilters()" in html
    assert "restorePersistedJobsKeywordFiltersIfNeeded()" in html


def test_tailor_session_prompt_uses_revision_advice_markdown(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-session-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Scientific ML Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-session-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    workspace.revision_advice_path.write_text(
        "# 修改建议\n\n- 保留 simulation-first, AI-enabled scientist 定位。\n\n# 发给 Codex Session 的指令\n\n请直接改 final tex。\n",
        encoding="utf-8",
    )
    pipeline_state = tailor_service.load_pipeline_state(workspace)
    pipeline_state["session_id"] = "session-123"
    pipeline_state["session_status"] = "ready"
    pipeline_state["session_established_at"] = datetime(2026, 4, 14, 18, 0, tzinfo=timezone.utc).isoformat()
    pipeline_state["revision_advice_status"] = "succeeded"
    pipeline_state["revision_advice_updated_at"] = datetime(2026, 4, 14, 18, 5, tzinfo=timezone.utc).isoformat()
    tailor_service._save_pipeline_state(workspace, pipeline_state)

    started: dict[str, object] = {}

    class DummyThread:
        def __init__(self, target, args, daemon, name):
            started["target"] = target
            started["args"] = args
            started["daemon"] = daemon
            started["name"] = name

        def start(self):
            started["started"] = True

    monkeypatch.setattr(main_module.threading, "Thread", DummyThread)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/session/prompt",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    latest_run = repository.latest_tailor_run_for_job(job.id or 0)
    assert payload["message"] == "已把右侧发送区内容发送给当前 Codex session。"
    assert latest_run is not None
    request_payload = json.loads(latest_run.request_payload)
    assert request_payload["prompt_source"] == "session_instruction.md"
    assert request_payload["instruction_text"] == "请直接改 final tex。"
    assert started["started"] is True


def test_run_revision_advice_route_does_not_auto_rebuild_session(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-revision-advice-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Revision Advice Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-revision-advice-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    pipeline_state = tailor_service.load_pipeline_state(workspace)
    pipeline_state["session_id"] = "existing-session-123"
    pipeline_state["session_status"] = "ready"
    pipeline_state["session_established_at"] = datetime(2026, 4, 14, 18, 0, tzinfo=timezone.utc).isoformat()
    tailor_service._save_pipeline_state(workspace, pipeline_state)

    started: dict[str, object] = {}

    class DummyThread:
        def __init__(self, target, args, daemon, name):
            started["target"] = target
            started["args"] = args
            started["daemon"] = daemon
            started["name"] = name

        def start(self):
            started["started"] = True

    monkeypatch.setattr(main_module.threading, "Thread", DummyThread)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/revision-advice",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    latest_run = repository.latest_tailor_run_for_job(job.id or 0)
    refreshed_state = tailor_service.load_pipeline_state(workspace)
    assert payload["message"] == "已开始重新生成修改建议：会复用当前 Session，必要时自动恢复。"
    assert payload["session"]["id"] == "existing-session-123"
    assert payload["session"]["status"] == "ready"
    assert latest_run is not None
    assert json.loads(latest_run.request_payload)["mode"] == "revision_advice"
    assert refreshed_state["session_id"] == "existing-session-123"
    assert refreshed_state["session_status"] == "ready"
    assert started["started"] is True


def test_revision_advice_reuses_latest_run_session_when_workspace_state_is_stale(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-revision-advice-session-fallback-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Fallback Session Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-revision-advice-session-fallback-job",
                description="Build scientific machine learning workflows for molecules.",
                score=81.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    stale_state = tailor_service.load_pipeline_state(workspace)
    stale_state["session_id"] = ""
    stale_state["session_status"] = "not_started"
    stale_state["session_established_at"] = None
    tailor_service._save_pipeline_state(workspace, stale_state)
    repository.create_tailor_run(
        TailorRun(
            job_id=job.id or 0,
            profile_slug=job.profile_slug,
            workspace_dir=str(workspace.workspace_dir),
            base_resume_path=workspace.base_resume_path,
            session_id="session-fallback-xyz",
            status="succeeded",
            current_step_key="session_prompt",
            last_message="previous session ready",
        )
    )

    class ImmediateThread:
        def __init__(self, target, args, daemon, name):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def start(self):
            self.target(*self.args)

    def fake_start_session(*args, **kwargs):
        raise AssertionError("should not start a fresh session when latest run already has session_id")

    def fake_run_revision_advice(job_arg, workspace_arg, *, session_id, pid_callback):
        assert session_id == "session-fallback-xyz"
        workspace_arg.revision_advice_path.write_text(
            "# 修改建议摘要\n- 收紧 summary\n\n# 发给 Codex Session 的指令\n## 修改目标\n- 收紧 summary\n",
            encoding="utf-8",
        )
        updated_state = tailor_service.load_pipeline_state(workspace_arg)
        updated_state["session_id"] = session_id
        updated_state["session_status"] = "ready"
        updated_state["revision_advice_status"] = "succeeded"
        tailor_service._save_pipeline_state(workspace_arg, updated_state)
        pid_callback("revision_advice", 4321, session_id)
        pid_callback("revision_advice", None, session_id)
        return "Revision advice done"

    monkeypatch.setattr(main_module.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(tailor_service, "start_session", fake_start_session)
    monkeypatch.setattr(tailor_service, "run_revision_advice", fake_run_revision_advice)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/revision-advice",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    latest_run = repository.latest_tailor_run_for_job(job.id or 0)
    refreshed_state = tailor_service.load_pipeline_state(workspace)
    assert payload["session"]["id"] == "session-fallback-xyz"
    assert payload["session"]["status"] == "ready"
    assert latest_run is not None
    assert latest_run.session_id == "session-fallback-xyz"
    assert latest_run.status == "succeeded"
    assert latest_run.last_message == "Revision advice done"
    assert refreshed_state["session_id"] == "session-fallback-xyz"
    assert refreshed_state["revision_advice_status"] == "succeeded"


def test_run_tailor_advice_route_returns_one_click_message(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-one-click-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="One Click Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-one-click-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    started: dict[str, object] = {}

    class DummyThread:
        def __init__(self, target, args, daemon, name):
            started["target"] = target
            started["args"] = args
            started["daemon"] = daemon
            started["name"] = name

        def start(self):
            started["started"] = True

    monkeypatch.setattr(main_module.threading, "Thread", DummyThread)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/advice",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    latest_run = repository.latest_tailor_run_for_job(job.id or 0)
    assert payload["message"] == "已开始一键生成：会复用或建立当前 Session，并生成修改建议。"
    assert latest_run is not None
    assert latest_run.current_step_key == "revision_advice"
    assert json.loads(latest_run.request_payload)["mode"] == "one_click_generate"
    assert started["started"] is True


def test_run_md_agent_route_is_removed(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-md-agent-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="MD Agent Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-md-agent-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/md-agent/revision_advice/review",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 404


def test_open_finder_route_uses_workspace_dir_on_macos(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-finder-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Scientific ML Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-finder-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    calls: list[list[str]] = []

    def fake_run(cmd, check):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/workspace/open-finder",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["message"] == "已在 Finder 中打开当前工作区。"
    assert calls == [["open", str(workspace.workspace_dir)]]


def test_reveal_tailor_artifact_route_uses_open_r_on_macos(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-reveal-artifact-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Reveal Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-reveal-artifact-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    workspace.session_instruction_path.write_text("请改 final tex。\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, check):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/artifact/session_instruction/reveal",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["message"] == "已在 Finder 中定位 session_instruction.md。"
    assert calls == [["open", "-R", str(workspace.session_instruction_path)]]


def test_reveal_tailor_skill_route_uses_open_r_on_macos(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-reveal-skill-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Reveal Skill Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-reveal-skill-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    calls: list[list[str]] = []

    def fake_run(cmd, check):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/skills/revision_advice/reveal",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["message"] == "已在 Finder 中定位 revision_advice.md。"
    assert calls == [["open", "-R", str(tailor_service.skill_path("revision_advice"))]]


def test_tailor_tasks_aggregate_runs_by_workspace(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-tailor-aggregate-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Aggregation Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-tailor-aggregate-job",
                description="Build scientific machine learning workflows for molecules.",
                score=82.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    for index in range(2):
        repository.create_tailor_run(
            main_module.TailorRun(
                job_id=job.id or 0,
                profile_slug=job.profile_slug,
                workspace_dir=str(workspace.workspace_dir),
                base_resume_path=workspace.base_resume_path,
                session_id=f"session-{index}",
                status="succeeded",
                last_message=f"run-{index}",
                created_at=datetime.now(timezone.utc) + timedelta(seconds=index),
                updated_at=datetime.now(timezone.utc) + timedelta(seconds=index),
            )
        )

    client = web_app.test_client()
    tailor_html = client.get("/tailor-tasks").get_data(as_text=True)
    dashboard_html = client.get("/dashboard").get_data(as_text=True)

    assert tailor_html.count("Aggregation Scientist") == 1
    assert "2 次运行" in tailor_html
    assert "Aggregation Scientist" in dashboard_html
    assert "2 次运行" in dashboard_html


def test_jobs_page_defaults_to_recent_sort_and_supports_recent_24h_filter(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    now = datetime.now(timezone.utc)
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-recent-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Recent Scientist",
                company="Example Labs",
                location_text="Cambridge, MA",
                city="",
                state="",
                country="",
                job_url="https://example.com/jobs/route-recent-job",
                description="Build scientific machine learning workflows for molecules.",
                score=32.0,
                last_refreshed_at=now,
            ),
            JobRecord(
                unique_key="route-old-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Older Scientist",
                company="Example Labs",
                location_text="Cambridge, MA",
                city="",
                state="",
                country="",
                job_url="https://example.com/jobs/route-old-job",
                description="Build scientific machine learning workflows for molecules.",
                score=81.0,
                last_refreshed_at=now - timedelta(hours=30),
            )
        ]
    )
    with Session(repository.engine) as session:
        recent_job = session.exec(select(JobRecord).where(JobRecord.unique_key == "route-recent-job")).one()
        old_job = session.exec(select(JobRecord).where(JobRecord.unique_key == "route-old-job")).one()
        recent_job.last_refreshed_at = now
        old_job.last_refreshed_at = now - timedelta(hours=30)
        session.add(recent_job)
        session.add(old_job)
        session.commit()

    client = web_app.test_client()
    jobs_response = client.get("/jobs")
    jobs_html = jobs_response.get_data(as_text=True)
    recent_response = client.get("/jobs?recent_hours=24")
    recent_html = recent_response.get_data(as_text=True)

    assert jobs_response.status_code == 200
    assert "最低分 0" in jobs_html
    assert "sort_by=score" in jobs_html
    assert "sort_by=recent" in jobs_html
    assert jobs_html.index("Recent Scientist") < jobs_html.index("Older Scientist")
    assert recent_response.status_code == 200
    assert "Recent Scientist" in recent_html
    assert "Older Scientist" not in recent_html


def test_marking_applied_job_adds_track_entry(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-apply-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Applied Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-apply-job",
                description="Build scientific machine learning workflows for molecules.",
                score=71.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    client = web_app.test_client()
    apply_response = client.post(
        f"/jobs/{job.id}/application",
        data={"action": "mark", "return_to": "/jobs"},
        follow_redirects=True,
    )
    jobs_html = apply_response.get_data(as_text=True)
    dashboard_html = client.get("/dashboard").get_data(as_text=True)
    tracker_html = client.get("/application-tracker").get_data(as_text=True)

    assert apply_response.status_code == 200
    assert "已标记为已投递。" in jobs_html
    assert "Applied Scientist" not in jobs_html
    assert "Applied Scientist" in dashboard_html
    assert "投递追踪" in dashboard_html
    assert "Applied Scientist" in tracker_html
    assert "关联职位" in tracker_html
    assert "<details" in tracker_html


def test_marking_applied_job_returns_json_for_async_jobs_page(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-apply-job-async",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Async Applied Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-apply-job-async",
                description="Build scientific machine learning workflows for molecules.",
                score=71.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    client = web_app.test_client()
    apply_response = client.post(
        f"/jobs/{job.id}/application",
        data={"action": "mark", "return_to": "/jobs"},
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
    )
    payload = apply_response.get_json()
    tracks = repository.list_application_tracks(limit=10)

    assert apply_response.status_code == 200
    assert payload is not None
    assert payload["ok"] is True
    assert payload["message"] == "已标记为已投递。"
    assert payload["job_id"] == job.id
    assert payload["remove_job"] is True
    assert "Async Applied Scientist" not in client.get("/jobs").get_data(as_text=True)
    assert len(tracks) == 1
    assert tracks[0]["track"].job_id == job.id


def test_jobs_page_title_opens_job_popup_and_keeps_tailor_link(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-popup-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Popup Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-popup-job",
                description="Popup target role.",
                score=72.0,
            ),
            JobRecord(
                unique_key="route-popup-fallback-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="career_site",
                title="Fallback Scientist",
                company="Hidden Labs",
                location_text="Austin, TX",
                city="Austin",
                state="TX",
                country="USA",
                job_url="",
                description="Fallback role without external URL.",
                score=61.0,
            ),
        ]
    )
    with Session(repository.engine) as session:
        popup_job = session.exec(
            select(JobRecord).where(JobRecord.unique_key == "route-popup-job")
        ).one()
        fallback_job = session.exec(
            select(JobRecord).where(JobRecord.unique_key == "route-popup-fallback-job")
        ).one()

    client = web_app.test_client()
    jobs_html = client.get("/jobs").get_data(as_text=True)

    assert popup_job is not None
    assert fallback_job is not None
    assert f'data-open-url="{popup_job.job_url}"' in jobs_html
    assert (
        f'href="/jobs/{popup_job.id}" class="primary-link">简历精修</a>'
        in jobs_html
    )
    assert (
        f'data-open-url="/jobs/{fallback_job.id}/preview"'
        in jobs_html
    )
    assert 'data-browser-window-route="/jobs/' in jobs_html
    assert 'window.resumeJobMonitor.openJobBrowserWindow(routeUrl, fallbackUrl' in jobs_html
    assert 'class="row-title row-title-button"' in jobs_html
    assert 'type="button"' in jobs_html
    assert 'window.resumeJobMonitor?.rt?.("manualOpenFallback"' in jobs_html
    assert 'window.resumeJobMonitor?.rt?.("jobWindowOpenFailed")' in jobs_html
    assert "window.open(" not in jobs_html
    assert '"about:blank"' not in jobs_html
    assert 'location.replace(fallbackUrl);' not in jobs_html
    assert 'data-job-popup-link' in jobs_html
    assert '岗位描述' in jobs_html


def test_job_preview_page_renders_local_description_and_original_link(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-preview-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Preview Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-preview-job",
                description="Line one.\n\nLine two.",
                explanation="Strong title overlap.",
                matched_keywords="scientific machine learning",
                score=77.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    client = web_app.test_client()
    response = client.get(f"/jobs/{job.id}/preview")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "岗位描述窗口" in html
    assert "这个窗口会被 Jobs 和 Tailor 页的“岗位描述”按钮重复复用。" in html
    assert "Line one." in html
    assert "Strong title overlap." in html
    assert '打开原始职位页' in html


def test_job_browser_window_marker_route_renders_marker_page(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()

    client = web_app.test_client()
    response = client.get("/jobs/browser-window-marker")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert main_module.JOB_BROWSER_WINDOW_MARKER_TITLE in html
    assert main_module.JOB_BROWSER_WINDOW_MARKER_TEXT in html
    assert "noindex,nofollow" in html


def test_jobs_page_supports_ajax_sorting_and_filter_refresh(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-scroll-apply-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Scroll Apply Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-scroll-apply-job",
                description="Apply fallback role.",
                score=68.0,
            )
        ]
    )

    client = web_app.test_client()
    jobs_html = client.get("/jobs").get_data(as_text=True)

    assert "new DOMParser().parseFromString(html, \"text/html\")" in jobs_html
    assert "window.history.pushState({ jobsView: true }, \"\", url);" in jobs_html
    assert "window.addEventListener(\"popstate\"" in jobs_html
    assert "replaceJobsNode(\"#jobs-filters\", nextDocument);" in jobs_html
    assert "replaceJobsNode(\"#jobs-table\", nextDocument);" in jobs_html
    assert "loadJobsView(buildJobsViewUrl(form));" in jobs_html
    assert 'const nativeFallbackScrollKey = "quickapply:jobs-native-fallback-scroll";' in jobs_html
    assert "const scrollRestoreSelector =" in jobs_html
    assert "form.matches(scrollRestoreSelector)" in jobs_html
    assert "form[method='post'], form[method='POST']" not in jobs_html
    assert 'window.resumeJobMonitor.openJobBrowserWindow(routeUrl, fallbackUrl' in jobs_html


def test_jobs_page_apply_form_has_native_fallback(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-apply-fallback-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Fallback Apply Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-apply-fallback-job",
                description="Apply fallback role.",
                score=68.0,
            )
        ]
    )

    client = web_app.test_client()
    jobs_html = client.get("/jobs").get_data(as_text=True)

    assert 'data-job-apply-form' in jobs_html
    assert 'HTMLFormElement.prototype.submit.call(form);' in jobs_html
    assert '异步提交失败，正在改用普通提交。' in jobs_html
    assert 'if (!form.matches("[data-job-apply-form]")) return;' in jobs_html
    assert 'rememberNativeFallbackScrollState(jobId);' in jobs_html
    assert 'class="add-term-form top-space-sm" data-native-scroll-restore' in jobs_html
    assert 'data-native-scroll-restore' in jobs_html
    assert 'data-job-apply-form data-native-scroll-restore' not in jobs_html
    assert 'data-job-action-form data-native-scroll-restore' not in jobs_html


def test_open_job_browser_window_route_uses_chrome_window_on_macos(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-browser-window-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Window Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://www.linkedin.com/jobs/view/route-browser-window-job",
                description="Open in browser window.",
                score=75.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    calls: list[list[str]] = []

    def fake_run(cmd, check, capture_output, text):
        calls.append(list(cmd))
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 0, stdout="chrome-window-123\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/open-browser-window",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert (
        payload["message"]
        == "已在专用 Chrome 岗位工作窗中打开当前 LinkedIn 职位，并自动尝试展开折叠内容。当前复用你的 Chrome 配置，扩展状态按浏览器原有设置保持。"
    )
    assert payload["opened_url"] == job.job_url
    assert payload["mode"] == "chrome_dedicated_window"
    assert payload["site_behavior"] == "linkedin_auto_expand"
    assert payload["plugin_mode"] == "reuse_chrome_profile_state"
    assert payload["fallback"] is False
    assert "warning" not in payload
    assert len(calls) == 2
    state_path = web_app.config["browser_window_state_path"]
    saved_state = main_module.load_browser_window_state(state_path)
    assert calls[0][0] == "osascript"
    assert calls[0][3] == job.job_url
    assert calls[0][4] == ""
    assert calls[0][5] == "http://localhost/jobs/browser-window-marker"
    assert calls[0][6] == "linkedin_auto_expand"
    assert calls[1][3] == "chrome-window-123"
    assert "show more" in calls[1][4]
    assert saved_state["window_id"] == "chrome-window-123"
    assert saved_state["marker_url"] == "http://localhost/jobs/browser-window-marker"


def test_open_url_in_dedicated_chrome_window_preserves_existing_window_bounds(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    state_path = tmp_path / "chrome_state.json"
    state_path.write_text(
        json.dumps({"window_id": "chrome-window-123"}, ensure_ascii=False),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_run(cmd, check, capture_output, text):
        calls.append(list(cmd))
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 0, stdout="chrome-window-123\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    result = main_module.open_url_in_dedicated_chrome_window(
        "https://example.com/jobs/preserve-window",
        state_path=state_path,
        marker_url="http://localhost/jobs/browser-window-marker",
        site_behavior="linkedin_auto_expand",
    )

    assert result.window_id == "chrome-window-123"
    assert result.warning == ""
    assert len(calls) == 2
    script = calls[0][2]
    expand_script = calls[1][2]
    assert "set createdNewWindow to false" in script
    assert "set markerUrl to item 3 of argv" in script
    assert "set siteBehavior to item 4 of argv" in script
    assert "set markerTabIndex to my findTabIndexByUrl(targetWindow, markerUrl)" in script
    assert "tell targetWindow to make new tab at end of tabs" in script
    assert "set targetTabIndex to my firstNonMarkerTabIndex(targetWindow, markerUrl)" in script
    assert "set active tab index of targetWindow to targetTabIndex" in script
    assert "set targetWindow to my findWindowById(existingWindowId)" in script
    assert "if my windowHasMarkerTab(targetWindow, markerUrl) is false then" in script
    assert "set targetWindow to my findWindowByMarker(markerUrl)" in script
    assert "on findWindowByMarker(markerUrl)" in script
    assert "on findTabIndexByUrl(targetWindow, expectedUrl)" in script
    assert "on firstNonMarkerTabIndex(targetWindow, markerUrl)" in script
    assert "if createdNewWindow then" in script
    assert 'if siteBehavior is "linkedin_auto_expand"' in script
    assert "set widthRatio to 0.68" in script
    assert "make new tab at end of tabs with properties {URL:targetUrl}" not in script
    assert "set active tab index of targetWindow to (index of targetTab)" not in script
    assert "set targetTabIndex to active tab index of targetWindow" in expand_script
    assert "execute targetTab javascript expandJavascript" in expand_script
    assert "on runExpandJavascript(targetTab, expandJavascript)" in expand_script
    assert calls[0][4] == "chrome-window-123"
    assert calls[0][5] == "http://localhost/jobs/browser-window-marker"
    assert calls[0][6] == "linkedin_auto_expand"
    assert calls[1][3] == "chrome-window-123"
    assert "show more" in calls[1][4]


def test_open_url_in_dedicated_chrome_window_ignores_state_from_other_marker(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    state_path = tmp_path / "chrome_state.json"
    state_path.write_text(
        json.dumps(
            {
                "window_id": "chrome-window-123",
                "marker_url": "http://127.0.0.1:9999/jobs/browser-window-marker",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_run(cmd, check, capture_output, text):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="chrome-window-999\n", stderr="")

    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    result = main_module.open_url_in_dedicated_chrome_window(
        "https://example.com/jobs/preserve-window",
        state_path=state_path,
        marker_url="http://localhost/jobs/browser-window-marker",
        site_behavior="default",
    )

    assert result.window_id == "chrome-window-999"
    assert result.warning == ""
    assert len(calls) == 1
    assert calls[0][4] == ""
    assert calls[0][5] == "http://localhost/jobs/browser-window-marker"
    assert calls[0][6] == "default"


def test_open_job_browser_window_route_returns_fallback_when_chrome_control_fails(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-browser-window-fallback-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="career_site",
                title="Window Fallback Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="",
                description="Fallback to preview.",
                score=63.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]

    def fake_run(cmd, check, capture_output, text):
        raise subprocess.CalledProcessError(1, cmd, stderr="chrome control failed")

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/open-browser-window",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["fallback"] is True
    assert payload["mode"] == "chrome_dedicated_window"
    assert payload["opened_url"].endswith(f"/jobs/{job.id}/preview")
    assert "Chrome 专用岗位工作窗打开失败" in payload["message"]
    assert "chrome control failed" in payload["message"]


def test_open_job_browser_window_route_returns_warning_when_linkedin_expand_fails(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-browser-window-warning-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Window Warning Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://www.linkedin.com/jobs/view/route-browser-window-warning-job",
                description="Open in browser window with LinkedIn warning.",
                score=77.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    calls: list[list[str]] = []

    def fake_run(cmd, check, capture_output, text):
        calls.append(list(cmd))
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 0, stdout="chrome-window-123\n", stderr="")
        raise subprocess.CalledProcessError(1, cmd, stderr="expand failed")

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/open-browser-window",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["fallback"] is False
    assert payload["site_behavior"] == "linkedin_auto_expand"
    assert payload["warning"] == "LinkedIn 自动展开附加步骤失败：expand failed"
    assert "LinkedIn 自动展开附加步骤失败：expand failed" in payload["message"]
    state_path = web_app.config["browser_window_state_path"]
    saved_state = main_module.load_browser_window_state(state_path)
    assert saved_state["window_id"] == "chrome-window-123"
    assert saved_state["marker_url"] == "http://localhost/jobs/browser-window-marker"


def test_open_job_browser_window_failure_keeps_saved_window_state(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-browser-window-keep-state-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Window State Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://www.linkedin.com/jobs/view/window-state-scientist",
                description="Keep saved state on failure.",
                score=72.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    state_path = web_app.config["browser_window_state_path"]
    state_path.write_text(
        json.dumps(
            {
                "window_id": "chrome-window-123",
                "marker_url": "http://localhost/jobs/browser-window-marker",
                "updated_at": "2026-04-18T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_run(cmd, check, capture_output, text):
        raise subprocess.CalledProcessError(1, cmd, stderr="chrome control failed")

    monkeypatch.setattr(main_module.sys, "platform", "darwin")
    monkeypatch.setattr(main_module.subprocess, "run", fake_run)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/open-browser-window",
        headers={
            "Accept": "application/json",
            "X-Requested-With": "quickapply",
        },
        data={},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["fallback"] is True
    assert main_module.load_browser_window_state(state_path)["window_id"] == "chrome-window-123"
    assert (
        main_module.load_browser_window_state(state_path)["marker_url"]
        == "http://localhost/jobs/browser-window-marker"
    )


def test_application_tracker_supports_manual_entry(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()

    client = web_app.test_client()
    tracker_response = client.post(
        "/application-tracker/manual",
        data={
            "title": "Manual Research Scientist",
            "company": "Hidden Labs",
            "source_site": "career_site",
            "profile_label": "Scientific ML",
            "job_url": "https://example.com/jobs/manual-role",
            "applied_at_local": "2026-04-13T09:15",
            "notes": "内推补录",
            "return_to": "/application-tracker?source_kind=manual",
        },
        follow_redirects=True,
    )
    tracker_html = tracker_response.get_data(as_text=True)

    assert tracker_response.status_code == 200
    assert "已新增手工投递追踪。" in tracker_html
    assert "Manual Research Scientist" in tracker_html
    assert "Hidden Labs" in tracker_html
    assert "手工录入" in tracker_html
    assert "career_site" in tracker_html


def test_application_tracker_supports_keyword_and_stage_filters(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    client = web_app.test_client()

    create_payloads = [
        {
            "title": "Manual Research Scientist",
            "company": "Hidden Labs",
            "source_site": "career_site",
            "profile_label": "Scientific ML",
            "job_url": "https://example.com/jobs/manual-hidden-submitted",
            "applied_at_local": "2026-04-13T09:15",
            "notes": "Hidden submitted",
            "return_to": "/application-tracker?source_kind=manual",
        },
        {
            "title": "Computational Scientist",
            "company": "Hidden Labs",
            "source_site": "career_site",
            "profile_label": "Scientific ML",
            "job_url": "https://example.com/jobs/manual-hidden-interviewed",
            "applied_at_local": "2026-04-13T10:15",
            "notes": "Hidden interviewed",
            "return_to": "/application-tracker?source_kind=manual",
        },
        {
            "title": "Data Scientist",
            "company": "Open Labs",
            "source_site": "career_site",
            "profile_label": "Scientific ML",
            "job_url": "https://example.com/jobs/manual-open-submitted",
            "applied_at_local": "2026-04-13T11:15",
            "notes": "Open submitted",
            "return_to": "/application-tracker?source_kind=manual",
        },
    ]
    for payload in create_payloads:
        response = client.post(
            "/application-tracker/manual",
            data=payload,
            follow_redirects=True,
        )
        assert response.status_code == 200

    repository = web_app.config["repository"]
    target_track = next(
        item["track"]
        for item in repository.list_application_tracks(source_kind="manual", limit=10)
        if item["track"].title == "Computational Scientist"
    )
    update_response = client.post(
        f"/application-tracker/{target_track.id}/events",
        data={
            "stage": "interviewed",
            "occurred_at_local": "2026-04-14T10:30",
            "notes": "Phone screen booked",
            "return_to": "/application-tracker?source_kind=manual",
        },
        follow_redirects=True,
    )
    assert update_response.status_code == 200

    filtered_response = client.get(
        "/application-tracker?source_kind=manual&keyword=hidden&stage=interviewed"
    )
    filtered_html = filtered_response.get_data(as_text=True)

    assert filtered_response.status_code == 200
    assert "Computational Scientist" in filtered_html
    assert "Manual Research Scientist" not in filtered_html
    assert "Data Scientist" not in filtered_html
    assert 'name="keyword"' in filtered_html
    assert 'value="hidden"' in filtered_html
    assert '<option value="interviewed" selected>Interviewed</option>' in filtered_html
    assert "关键词：hidden" in filtered_html
    assert "Interviewed" in filtered_html
    assert (
        'name="return_to" value="/application-tracker?source_kind=manual&amp;keyword=hidden&amp;stage=interviewed"'
        in filtered_html
    )


def test_application_track_daily_counts_build_expected_series(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="timeline-linked-applied",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Timeline Applied Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/timeline-linked-applied",
                description="Timeline role.",
                score=70.0,
            ),
            JobRecord(
                unique_key="timeline-linked-dismissed",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Timeline Dismissed Scientist",
                company="Review Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/timeline-linked-dismissed",
                description="Timeline dismissed role.",
                score=68.0,
            ),
        ]
    )
    with Session(repository.engine) as session:
        job_applied = session.exec(
            select(JobRecord).where(JobRecord.unique_key == "timeline-linked-applied")
        ).one()
        job_dismissed = session.exec(
            select(JobRecord).where(JobRecord.unique_key == "timeline-linked-dismissed")
        ).one()
        job_applied_id = job_applied.id or 0
        job_applied.first_seen_at = datetime(2026, 4, 14, 13, 0, tzinfo=timezone.utc)
        job_dismissed.first_seen_at = datetime(2026, 4, 15, 13, 0, tzinfo=timezone.utc)
        job_dismissed.dismissed_at = datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)
        session.add(job_applied)
        session.add(job_dismissed)
        session.commit()

    repository.sync_application_track_for_job(
        job_applied_id,
        applied_at=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
    )
    repository.create_manual_application_track(
        ApplicationTrack(
            source_kind="manual",
            title="Manual Timeline Scientist",
            company="Hidden Labs",
            source_site="career_site",
            profile_label="Scientific ML",
            job_url="https://example.com/jobs/manual-timeline",
            notes="Manual timeline entry",
            applied_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        )
    )

    reference_time = datetime(2026, 4, 20, 18, 0, tzinfo=timezone.utc)
    timeline_7d = repository.application_track_daily_counts(
        range_key="7d",
        reference_time=reference_time,
    )
    timeline_30d = repository.application_track_daily_counts(
        range_key="30d",
        reference_time=reference_time,
    )
    timeline_month = repository.application_track_daily_counts(
        range_key="month",
        reference_time=reference_time,
    )
    timeline_all = repository.application_track_daily_counts(
        range_key="all",
        reference_time=reference_time,
    )

    assert timeline_7d["range_key"] == "7d"
    assert timeline_7d["labels"][0] == "2026-04-14"
    assert timeline_7d["labels"][-1] == "2026-04-20"
    assert timeline_7d["totals"] == {
        "applied": 2,
        "crawled": 2,
        "reviewed": 2,
        "dismissed": 1,
    }
    assert timeline_7d["series"]["applied"][0] == 1
    assert timeline_7d["series"]["applied"][1] == 1
    assert timeline_7d["series"]["crawled"][0] == 1
    assert timeline_7d["series"]["crawled"][1] == 1
    assert timeline_7d["series"]["reviewed"][0] == 1
    assert timeline_7d["series"]["reviewed"][1] == 1
    assert timeline_7d["series"]["dismissed"][1] == 1
    assert timeline_7d["max_value"] == 1
    assert timeline_30d["labels"][0] == "2026-03-22"
    assert timeline_month["labels"][0] == "2026-04-01"
    assert timeline_all["labels"][0] == "2026-04-14"
    assert timeline_all["labels"][-1] == "2026-04-20"


def test_application_tracker_renders_chart_and_preserves_chart_range(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="tracker-chart-linked-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Tracker Chart Linked Job",
                company="Linked Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/tracker-chart-linked-job",
                description="Linked job for tracker chart.",
                score=72.0,
            )
        ]
    )
    with Session(repository.engine) as session:
        linked_job = session.exec(
            select(JobRecord).where(JobRecord.unique_key == "tracker-chart-linked-job")
        ).one()
        linked_job_id = linked_job.id or 0
        linked_job.first_seen_at = datetime(2026, 4, 14, 13, 0, tzinfo=timezone.utc)
        session.add(linked_job)
        session.commit()

    repository.sync_application_track_for_job(
        linked_job_id,
        applied_at=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
    )
    repository.create_manual_application_track(
        ApplicationTrack(
            source_kind="manual",
            title="Tracker Chart Manual Job",
            company="Hidden Labs",
            source_site="career_site",
            profile_label="Scientific ML",
            job_url="https://example.com/jobs/tracker-chart-manual-job",
            notes="Manual chart entry",
            applied_at=datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc),
        )
    )

    client = web_app.test_client()
    response = client.get(
        "/application-tracker?source_kind=manual&keyword=hidden&stage=submitted&chart_range=30d"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-tracker-chart-range="30d"' in html
    assert 'name="chart_range" value="30d"' in html
    assert 'href="/application-tracker?chart_range=30d"' in html
    assert 'data-series-key="applied"' in html
    assert 'data-series-total="2"' in html
    assert 'data-series-key="crawled"' in html
    assert 'data-series-total="1"' in html
    assert 'class="tracker-chart-toggle active"' in html
    assert "Manual Add" not in html


def test_application_tracker_invalid_chart_range_falls_back_to_all(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()

    client = web_app.test_client()
    response = client.get("/application-tracker?chart_range=not-valid")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-tracker-chart-range="all"' in html


def test_application_tracker_invalid_stage_filter_falls_back_to_all(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()

    client = web_app.test_client()
    tracker_response = client.post(
        "/application-tracker/manual",
        data={
            "title": "Manual Research Scientist",
            "company": "Hidden Labs",
            "source_site": "career_site",
            "profile_label": "Scientific ML",
            "job_url": "https://example.com/jobs/manual-role",
            "applied_at_local": "2026-04-13T09:15",
            "notes": "内推补录",
            "return_to": "/application-tracker",
        },
        follow_redirects=True,
    )
    assert tracker_response.status_code == 200

    filtered_response = client.get("/application-tracker?stage=oops")
    filtered_html = filtered_response.get_data(as_text=True)

    assert filtered_response.status_code == 200
    assert "Manual Research Scientist" in filtered_html
    assert '<option value="" selected>全部</option>' in filtered_html
    assert "关键词：" not in filtered_html
    assert 'value="oops"' not in filtered_html


def test_jobs_support_company_exclusion_and_restore(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-exclude-job-1",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Exclude Me",
                company="Noise Corp",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-exclude-job-1",
                description="Build scientific machine learning workflows for molecules.",
                score=62.0,
            ),
            JobRecord(
                unique_key="route-exclude-job-2",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="indeed",
                title="Keep Me",
                company="Signal Labs",
                location_text="Austin, TX",
                city="Austin",
                state="TX",
                country="USA",
                job_url="https://example.com/jobs/route-exclude-job-2",
                description="Build scientific machine learning workflows for molecules.",
                score=66.0,
            ),
        ]
    )
    exclude_job = next(job for job in repository.list_jobs(limit=10) if job.company == "Noise Corp")

    client = web_app.test_client()
    excluded_response = client.post(
        f"/jobs/{exclude_job.id}/exclude-company",
        data={"return_to": "/jobs"},
        follow_redirects=True,
    )
    excluded_html = excluded_response.get_data(as_text=True)
    excluded_company = repository.list_excluded_companies()[0]

    restored_response = client.post(
        f"/jobs/excluded-companies/{excluded_company.id}/delete",
        data={"return_to": "/jobs"},
        follow_redirects=True,
    )
    restored_html = restored_response.get_data(as_text=True)

    assert excluded_response.status_code == 200
    assert "已排除公司 Noise Corp" in excluded_html
    assert "Exclude Me" not in excluded_html
    assert "Keep Me" in excluded_html
    assert "Noise Corp" in excluded_html
    assert restored_response.status_code == 200
    assert "已移除排除公司。" in restored_html
    assert "Exclude Me" in restored_html
    assert "Keep Me" in restored_html


def test_tailor_run_api_returns_pipeline_workspace_state(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-tailor-api-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Pipeline Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-tailor-api-job",
                description="Build scientific machine learning workflows for molecules.",
                score=77.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    pipeline_state = tailor_service.load_pipeline_state(workspace)
    pipeline_state["current_step"] = "tailor_loop"
    pipeline_state["session_id"] = "session-123"
    pipeline_state["session_status"] = "ready"
    pipeline_state["session_established_at"] = datetime(2026, 4, 14, 12, 30, tzinfo=timezone.utc).isoformat()
    for step in pipeline_state["steps"]:
        if step["key"] == "setup":
            step["status"] = "succeeded"
            step["message"] = "setup done"
        elif step["key"] == "matching":
            step["status"] = "succeeded"
            step["message"] = "matching done"
        elif step["key"] == "tailor_loop":
            step["status"] = "running"
            step["message"] = "正在做 Tailor Loop"
            step["started_at"] = datetime.now(timezone.utc).isoformat()
    workspace.pipeline_state_path.write_text(
        json.dumps(pipeline_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    workspace.matching_analysis_path.write_text('{"fit":"high"}\n', encoding="utf-8")
    workspace.tailored_resume_path.write_text("% tailored\n", encoding="utf-8")
    workspace.fact_check_report_path.write_text('{"passed": false}\n', encoding="utf-8")
    workspace.final_resume_path.write_text("% final\n", encoding="utf-8")
    workspace.final_resume_pdf_path.write_text("pdf", encoding="utf-8")
    workspace.diff_path.write_text("% diff\n", encoding="utf-8")
    workspace.diff_pdf_path.write_text("diff-pdf", encoding="utf-8")
    workspace.vibe_review_path.write_text("# vibe\n", encoding="utf-8")
    workspace.step_logs["tailor_loop"].write_text("tailor-loop log\n", encoding="utf-8")

    run = repository.create_tailor_run(
        main_module.TailorRun(
            job_id=job.id or 0,
            profile_slug=job.profile_slug,
            workspace_dir=str(workspace.workspace_dir),
            base_resume_path=workspace.base_resume_path,
            session_id="session-123",
            status="running",
            result_json=json.dumps(pipeline_state, ensure_ascii=False),
            last_message="正在跑 Tailor Loop",
        )
    )

    client = web_app.test_client()
    response = client.get(f"/api/tailor-runs/{run.id}")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "running"
    assert payload["session_id"] == "session-123"
    assert payload["session_status"] == "ready"
    assert payload["session_established_at"] == "2026-04-14T12:30:00+00:00"
    assert payload["current_step_key"] == "tailor_loop"
    assert payload["current_step_label"] == "Tailor Loop"
    assert payload["matching_analysis_text"] == '{\n  "fit": "high"\n}'
    assert payload["tailored_resume_text"] == "% tailored\n"
    assert payload["fact_check_text"] == '{\n  "passed": false\n}'
    assert payload["final_resume_text"] == "% final\n"
    assert payload["diff_text"] == "% diff\n"
    assert payload["vibe_review_text"] == "# vibe\n"
    assert payload["pdf_ready"]["final_pdf"] is True
    assert payload["pdf_ready"]["diff_pdf"] is True
    assert payload["current_step_log_text"] == "tailor-loop log\n"


def test_final_prompt_route_reuses_existing_session(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-final-prompt-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Prompt Scientist",
                company="Prompt Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-final-prompt-job",
                description="Build scientific machine learning workflows for molecules.",
                score=84.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    workspace.final_resume_path.write_text("% final\n", encoding="utf-8")
    pipeline_state = tailor_service.load_pipeline_state(workspace)
    pipeline_state["session_id"] = "session-xyz"
    pipeline_state["session_status"] = "ready"
    for step in pipeline_state["steps"]:
        step["status"] = "succeeded"
        step["message"] = f"{step['key']} done"
    workspace.pipeline_state_path.write_text(
        json.dumps(pipeline_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    run = repository.create_tailor_run(
        main_module.TailorRun(
            job_id=job.id or 0,
            profile_slug=job.profile_slug,
            workspace_dir=str(workspace.workspace_dir),
            base_resume_path=workspace.base_resume_path,
            session_id="session-xyz",
            status="succeeded",
            result_json=json.dumps(pipeline_state, ensure_ascii=False),
        )
    )

    class ImmediateThread:
        def __init__(self, *, target, args=(), kwargs=None, daemon=None, name=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            self.target(*self.args, **self.kwargs)

    def fake_run_final_resume_prompt(job, workspace, *, instruction_text, session_id, pid_callback):
        pid_callback("final_prompt", 12345, session_id)
        workspace.final_resume_path.write_text("% final updated\n", encoding="utf-8")
        workspace.final_resume_pdf_path.write_text("pdf", encoding="utf-8")
        workspace.diff_path.write_text("% diff\n", encoding="utf-8")
        workspace.diff_pdf_path.write_text("pdf", encoding="utf-8")
        pid_callback("final_prompt", None, session_id)
        return ("Final prompt done", session_id)

    monkeypatch.setattr(main_module.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(tailor_service, "run_final_resume_prompt", fake_run_final_resume_prompt)

    client = web_app.test_client()
    response = client.post(
        f"/jobs/{job.id}/tailor/final-prompt",
        data={"instruction_text": "Please tighten the summary."},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    updated_run = repository.latest_tailor_run_for_job(job.id or 0)

    assert response.status_code == 200
    assert "已把右侧发送区内容发送给当前 Codex session。" in html
    assert updated_run is not None
    assert updated_run.status == "succeeded"
    assert updated_run.current_step_key == "session_prompt"
    assert updated_run.session_id == "session-xyz"
    assert updated_run.last_message == "Final prompt done"
    refreshed_workspace = tailor_service.ensure_workspace(job)
    assert refreshed_workspace.session_instruction_text.strip() == "Please tighten the summary."


def test_application_tracker_supports_stage_event_updates(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()

    client = web_app.test_client()
    tracker_response = client.post(
        "/application-tracker/manual",
        data={
            "title": "Manual Research Scientist",
            "company": "Hidden Labs",
            "source_site": "career_site",
            "profile_label": "Scientific ML",
            "job_url": "https://example.com/jobs/manual-role",
            "applied_at_local": "2026-04-13T09:15",
            "notes": "内推补录",
            "return_to": "/application-tracker?source_kind=manual",
        },
        follow_redirects=True,
    )
    assert tracker_response.status_code == 200

    html = tracker_response.get_data(as_text=True)
    assert "Submitted" in html

    repository = web_app.config["repository"]
    track = repository.list_application_tracks(source_kind="manual", limit=10)[0]["track"]

    updated_response = client.post(
        f"/application-tracker/{track.id}/events",
        data={
            "stage": "interviewed",
            "occurred_at_local": "2026-04-14T10:30",
            "notes": "Phone screen booked",
            "return_to": "/application-tracker?source_kind=manual",
        },
        follow_redirects=True,
    )
    updated_html = updated_response.get_data(as_text=True)

    assert updated_response.status_code == 200
    assert "已更新到 Interviewed。" in updated_html
    assert "Phone screen booked" in updated_html
    assert "Interviewed" in updated_html


def test_delete_tailor_run_removes_workspace(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    tailor_service = web_app.config["tailor_service"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-tailor-delete-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Delete Scientist",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-tailor-delete-job",
                description="Build scientific machine learning workflows for molecules.",
                score=77.0,
            )
        ]
    )
    job = repository.list_jobs(limit=1)[0]
    workspace = tailor_service.ensure_workspace(job)
    run = repository.create_tailor_run(
        main_module.TailorRun(
            job_id=job.id or 0,
            profile_slug=job.profile_slug,
            workspace_dir=str(workspace.workspace_dir),
            base_resume_path=workspace.base_resume_path,
            status="stopped",
        )
    )

    client = web_app.test_client()
    response = client.post(
        f"/tailor-runs/{run.id}/delete",
        data={"return_to": f"/jobs/{job.id}"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert repository.get_tailor_run(run.id or 0) is None
    assert not workspace.workspace_dir.exists()


def test_crawler_supports_profile_add_and_delete(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    client = web_app.test_client()

    add_response = client.post(
        "/profiles",
        data={
            "redirect_to": "crawler",
            "label": "Protein Modeling",
            "slug": "",
            "search_terms": '"protein modeling" machine learning',
            "locations": "Remote | Boston, MA",
            "default_resume_file": str(tmp_path / "resume.tex"),
            "sites": ["linkedin", "indeed"],
        },
        follow_redirects=True,
    )
    add_html = add_response.get_data(as_text=True)

    delete_response = client.post(
        "/profiles/protein-modeling/delete",
        data={"redirect_to": "crawler"},
        follow_redirects=True,
    )
    delete_html = delete_response.get_data(as_text=True)

    assert add_response.status_code == 200
    assert "已新增搜索画像：protein-modeling。" in add_html
    assert "Protein Modeling" in add_html
    assert delete_response.status_code == 200
    assert "已移除搜索画像：protein-modeling。" in delete_html
    assert "Protein Modeling" not in delete_html


def test_dismissed_job_disappears_from_jobs_and_stays_hidden_after_upsert(tmp_path, monkeypatch) -> None:
    config_path = _write_test_config(tmp_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    import app.main as main_module

    main_module = importlib.reload(main_module)
    web_app = main_module.create_app()
    repository = web_app.config["repository"]
    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-dismiss-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Dismiss Me",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-dismiss-job",
                description="Build scientific machine learning workflows for molecules.",
                score=68.0,
            ),
            JobRecord(
                unique_key="route-keep-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="indeed",
                title="Keep Me",
                company="Example Labs",
                location_text="Austin, TX",
                city="Austin",
                state="TX",
                country="USA",
                job_url="https://example.com/jobs/route-keep-job",
                description="Build scientific machine learning workflows for molecules.",
                score=67.0,
            ),
        ]
    )
    dismiss_job = next(job for job in repository.list_jobs(limit=10) if job.unique_key == "route-dismiss-job")

    client = web_app.test_client()
    dismiss_response = client.post(
        f"/jobs/{dismiss_job.id}/dismiss",
        data={"return_to": "/jobs"},
        follow_redirects=True,
    )
    jobs_html = dismiss_response.get_data(as_text=True)

    repository.upsert_jobs(
        [
            JobRecord(
                unique_key="route-dismiss-job",
                profile_slug="scientific-ml",
                profile_label="Scientific ML",
                search_term='"scientific machine learning"',
                source_site="linkedin",
                title="Dismiss Me",
                company="Example Labs",
                location_text="Chicago, IL",
                city="Chicago",
                state="IL",
                country="USA",
                job_url="https://example.com/jobs/route-dismiss-job",
                description="Refetched description.",
                score=91.0,
            )
        ]
    )
    refreshed_jobs_html = client.get("/jobs").get_data(as_text=True)

    assert dismiss_response.status_code == 200
    assert "已标记为不合适" in jobs_html
    assert "Dismiss Me" not in jobs_html
    assert "Keep Me" in jobs_html
    assert "Dismiss Me" not in refreshed_jobs_html
    assert "Keep Me" in refreshed_jobs_html

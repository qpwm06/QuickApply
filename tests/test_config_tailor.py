from __future__ import annotations

import pytest
import yaml

from app.config import (
    ROOT_DIR,
    add_search_profile,
    delete_search_profile,
    load_settings,
    save_profile_locations,
    save_search_terms,
)
from app.location_utils import (
    infer_country_label,
    linkedin_jobs_search_url,
    normalize_selected_countries,
    source_site_home_url,
)
from app.models import JobRecord
from app.resume_profile import build_resume_profile
from app.tailor_service import TailorService, split_revision_advice


def test_save_search_terms_updates_yaml_file(tmp_path) -> None:
    config_path = tmp_path / "search_profiles.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "search_profiles": [
                    {
                        "slug": "scientific-ml",
                        "search_terms": ["old term"],
                        "search_term_weights": {"old term": 0.8},
                    }
                ]
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    save_search_terms(
        "scientific-ml",
        ["  new term  ", "new term", "", "another query"],
        config_path=config_path,
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["search_profiles"][0]["search_terms"] == ["new term", "another query"]
    assert saved["search_profiles"][0]["search_term_weights"] == {
        "new term": 1.0,
        "another query": 1.0,
    }


def test_save_profile_locations_updates_yaml_file(tmp_path) -> None:
    config_path = tmp_path / "search_profiles.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "search_profiles": [
                    {
                        "slug": "scientific-ml",
                        "locations": ["Remote"],
                    }
                ]
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    save_profile_locations(
        "scientific-ml",
        ["  United States  ", "Chicago, IL", "United States"],
        config_path=config_path,
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["search_profiles"][0]["locations"] == ["United States", "Chicago, IL"]


def test_load_settings_preserves_sqlite_memory_url(tmp_path) -> None:
    config_path = tmp_path / "search_profiles.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "app": {"database_url": "sqlite:///:memory:"},
                "resume_profile": {
                    "name": "Memory DB",
                    "summary": "test",
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_path)

    assert settings.app.database_url == "sqlite:///:memory:"


def test_add_and_delete_search_profile_updates_yaml_file(tmp_path) -> None:
    config_path = tmp_path / "search_profiles.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "search_profiles": [
                    {
                        "slug": "scientific-ml",
                        "label": "Scientific ML",
                        "search_terms": ["old term"],
                        "locations": ["Remote"],
                        "sites": ["linkedin"],
                    }
                ]
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    added_slug = add_search_profile(
        label="Protein Modeling",
        search_terms=['"protein modeling" machine learning'],
        locations=["Remote", "Boston, MA"],
        sites=["linkedin", "indeed"],
        default_resume_file="examples/resumes/test_resume.tex",
        config_path=config_path,
    )
    delete_search_profile("scientific-ml", config_path=config_path)

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert added_slug == "protein-modeling"
    assert len(saved["search_profiles"]) == 1
    assert saved["search_profiles"][0]["slug"] == "protein-modeling"
    assert saved["search_profiles"][0]["sites"] == ["linkedin", "indeed"]
    assert saved["search_profiles"][0]["search_term_weights"] == {
        '"protein modeling" machine learning': 1.0,
    }


def test_add_search_profile_defaults_to_united_states_when_locations_missing(tmp_path) -> None:
    config_path = tmp_path / "search_profiles.yaml"
    config_path.write_text(
        yaml.safe_dump({"search_profiles": []}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    added_slug = add_search_profile(
        label="Computational Chemistry",
        search_terms=['"computational chemist"'],
        config_path=config_path,
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert added_slug == "computational-chemistry"
    assert saved["search_profiles"][0]["locations"] == ["United States"]


def test_location_country_helpers_cover_defaults() -> None:
    assert infer_country_label(location_text="Shanghai, China") == "China"
    assert infer_country_label(country="United States", location_text="Remote") == "USA"
    assert infer_country_label(location_text="Cambridge, MA") == "USA"
    assert infer_country_label(location_text="Portland, Oregon Metropolitan Area") == "USA"
    assert infer_country_label(location_text="Berlin, Germany") == "Other"
    assert infer_country_label() == "Unknown"
    assert normalize_selected_countries([]) == ["China", "USA"]
    assert normalize_selected_countries(["USA", "Other", "Mars"]) == ["USA", "Other"]
    assert source_site_home_url("linkedin") == "https://www.linkedin.com/jobs/"
    assert linkedin_jobs_search_url('"protein modeling"', "Boston, MA").startswith(
        "https://www.linkedin.com/jobs/search/?"
    )


def test_tailor_service_creates_and_updates_workspace(tmp_path) -> None:
    settings = load_settings()
    settings.app.workspaces_dir = str(tmp_path / "Role")
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    job = JobRecord(
        id=321,
        unique_key="job-321",
        profile_slug="growth-marketing",
        profile_label="Growth Marketing + Demand Gen",
        search_term='"growth marketing manager" saas',
        source_site="linkedin",
        title="Growth Marketing Manager",
        company="Example Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/321",
        description="Own lifecycle automation, paid programs, and pipeline reporting for a SaaS team.",
    )

    workspace = service.ensure_workspace(job)

    assert workspace.workspace_dir.exists()
    assert workspace.workspace_dir.parent == (tmp_path / "Role")
    assert workspace.role_path.exists()
    assert workspace.notes_path.exists()
    assert workspace.base_resume_copy_path.exists()
    assert workspace.base_resume_copy_path.name == "cv_template.tex"
    assert workspace.pipeline_state_path.exists()
    assert workspace.base_resume_path.endswith("taylor_brooks_growth_marketing.tex")
    assert workspace.revision_advice_path.name == "resume_revision_advice.md"
    assert workspace.session_instruction_path.name == "session_instruction.md"
    assert workspace.matching_analysis_path.name == "matching_analysis.json"
    assert workspace.fact_check_report_path.name == "fact_check_report.json"
    assert workspace.final_resume_path.name.startswith("cv-ExampleLabs-")
    assert workspace.final_resume_pdf_path.name.startswith("cv-ExampleLabs-")
    assert workspace.diff_path.name == "diff.tex"
    assert workspace.diff_pdf_path.name == "diff.pdf"
    assert workspace.vibe_review_path.name == "vibe_review.md"
    assert "Growth Marketing Manager" in workspace.role_markdown

    updated_role = "# Tailor focus\n\n- Lead with lifecycle automation and pipeline outcomes."
    updated_notes = "# User Notes\n\n- Stress customer stories, renewal proof, and dashboard ownership."
    updated_resume = "examples/resumes/taylor_brooks_customer_success.tex"
    updated_instruction = "请把 summary 收窄到 revenue-minded GTM operator。"
    updated = service.save_workspace(
        job,
        base_resume_path=updated_resume,
        role_markdown=updated_role,
        user_notes=updated_notes,
        session_instruction_text=updated_instruction,
    )

    expected_resume_text = (ROOT_DIR / updated_resume).resolve().read_text(encoding="utf-8")
    assert updated.base_resume_path == updated_resume
    assert updated.role_markdown == updated_role + "\n"
    assert updated.user_notes == updated_notes + "\n"
    assert updated.session_instruction_text == updated_instruction + "\n"
    assert updated.base_resume_copy_path.read_text(encoding="utf-8") == expected_resume_text
    updated_pipeline_state = service.load_pipeline_state(updated)
    assert updated_pipeline_state["selected_resume_path"] == updated_resume
    matching_step = next(
        step for step in updated_pipeline_state["steps"]
        if step["key"] == "matching"
    )
    assert matching_step["status"] == "pending"
    assert [step["key"] for step in updated_pipeline_state["steps"]] == [
        "setup",
        "matching",
        "tailor_loop",
        "final_proof",
        "vibe_review",
    ]
    assert updated_pipeline_state["revision_advice_status"] in {"idle", "stale"}


def test_tailor_service_session_prompt_uses_role_md_not_snapshot(tmp_path) -> None:
    settings = load_settings()
    settings.app.workspaces_dir = str(tmp_path / "Role")
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    job = JobRecord(
        id=323,
        unique_key="job-323",
        profile_slug="customer-success",
        profile_label="Customer Success + Expansion",
        search_term='"customer success manager" saas',
        source_site="linkedin",
        title="Customer Success Manager",
        company="Example Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/323",
        description="Customer success role with onboarding, renewal health, and expansion planning.",
    )
    workspace = service.ensure_workspace(job)

    prompt = service._build_session_prompt_instruction(  # noqa: SLF001
        job,
        workspace,
        (
            "## 修改目标\n"
            "- 收窄 summary，前置 onboarding 与 renewal outcomes。\n\n"
            "## 必做项\n"
            "- 保持 LaTeX 可编译。\n"
        ),
    )
    revision_prompt = service._build_revision_advice_prompt(job, workspace)  # noqa: SLF001

    assert service.skill_path("revision_advice") is not None
    assert ".codex/skills/resume-tailor/revision_advice.md" in str(service.skill_path("revision_advice"))
    assert service.skill_path("session_send") is not None
    assert service.skill_path("session_start") is None
    assert "job_snapshot.json 只做留档，不是主输入" in prompt
    assert "job_snapshot.json 只做留档，不是主输入" in revision_prompt
    assert "role.md 是当前岗位信息的主文档" in prompt
    assert "这套工作台不依赖外部自动发现 skill" in prompt
    assert "当前不读取 .claude/agents" in revision_prompt
    assert "当前不读取 .claude/agents" in prompt
    assert "## 修改目标" in prompt
    assert "把 `## 修改目标` 当作这一轮的主线" in prompt
    assert "这是当前已建立 Codex session 的 follow-up turn" in prompt
    assert "不要重新 bootstrap" in prompt
    assert "这是当前已建立 Codex session 的后续回合" in revision_prompt
    assert "可选基础模板" not in revision_prompt
    assert "# 发给 Codex Session 的指令" in revision_prompt
    assert "当前主链接" in revision_prompt
    assert "underline 强调点" in revision_prompt
    assert "只写 `resume_revision_advice.md`" in revision_prompt
    assert "不允许修改 .codex、.claude" in prompt
    assert "role-project-matcher.md" not in prompt
    assert "role-project-matcher.md" not in revision_prompt
    assert "这一步不读取外部 skill 文件，而是使用内置的固定规则来建立或恢复同一个 Codex session" in service._build_session_start_prompt(job, workspace)  # noqa: SLF001
    assert "Built a 14-account customer reference bench" in revision_prompt


def test_revision_advice_prefers_final_resume_when_available(tmp_path) -> None:
    settings = load_settings()
    settings.app.workspaces_dir = str(tmp_path / "Role")
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    job = JobRecord(
        id=324,
        unique_key="job-324",
        profile_slug="customer-success",
        profile_label="Customer Success + Expansion",
        search_term='"customer success manager" saas',
        source_site="linkedin",
        title="Customer Success Manager",
        company="Example Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/324",
        description="Customer success role with onboarding and renewals.",
    )
    workspace = service.ensure_workspace(job)
    workspace.final_resume_path.write_text(
        (
            "https://www.linkedin.com/in/final-version\n"
            "\\section*{Selected Wins}\n"
            "\\item Recovered $1.2M ARR through renewal planning.\n"
            "\\underline{Final-version emphasis}\n"
        ),
        encoding="utf-8",
    )

    revision_prompt = service._build_revision_advice_prompt(job, workspace)  # noqa: SLF001

    assert str(workspace.final_resume_path) in revision_prompt
    assert "当前简历来源: final tex" in revision_prompt
    assert "https://www.linkedin.com/in/final-version" in revision_prompt
    assert "Recovered $1.2M ARR through renewal planning." in revision_prompt
    assert "Final-version emphasis" in revision_prompt


def test_split_revision_advice_extracts_session_instruction() -> None:
    markdown_text = (
        "# 修改建议\n\n"
        "## Summary\n"
        "- 前置 simulation-first framing。\n\n"
        "# 发给 Codex Session 的指令\n\n"
        "请直接修改 final tex，并保持 LaTeX 可编译。\n"
    )

    summary_text, session_instruction = split_revision_advice(markdown_text)

    assert "发给 Codex Session 的指令" not in summary_text
    assert "Summary" in summary_text
    assert session_instruction == "请直接修改 final tex，并保持 LaTeX 可编译。"


def test_run_revision_advice_populates_session_instruction_and_reuses_session(
    tmp_path,
    monkeypatch,
) -> None:
    settings = load_settings()
    settings.app.workspaces_dir = str(tmp_path / "Role")
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    job = JobRecord(
        id=324,
        unique_key="job-324",
        profile_slug="scientific-ml",
        profile_label="Scientific ML + Molecular Modeling",
        search_term='"scientific machine learning"',
        source_site="linkedin",
        title="Scientific ML Scientist",
        company="Auto Session Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/324",
        description="Work on molecular simulation and machine learning potentials.",
    )
    workspace = service.ensure_workspace(job)
    observed: dict[str, str] = {}

    def fake_run_workspace_action(**kwargs):
        observed["session_id"] = kwargs["session_id"]
        workspace.revision_advice_path.write_text(
            "# 修改建议\n\n- 收窄 summary。\n\n# 发给 Codex Session 的指令\n\n请直接修改 final tex。\n",
            encoding="utf-8",
        )
        return ("修改建议已生成。", "existing-session-123")

    monkeypatch.setattr(service, "_run_workspace_action", fake_run_workspace_action)

    message = service.run_revision_advice(
        job,
        workspace,
        session_id="existing-session-123",
    )
    refreshed_workspace = service.ensure_workspace(job)
    pipeline_state = service.load_pipeline_state(refreshed_workspace)

    assert "修改建议已生成。" in message
    assert observed["session_id"] == "existing-session-123"
    assert refreshed_workspace.session_instruction_text.strip() == "请直接修改 final tex。"
    assert pipeline_state["revision_advice_status"] == "succeeded"
    assert pipeline_state["session_status"] == "ready"
    assert pipeline_state["session_id"] == "existing-session-123"


def test_run_revision_advice_requires_existing_session_id(tmp_path) -> None:
    settings = load_settings()
    settings.app.workspaces_dir = str(tmp_path / "Role")
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    job = JobRecord(
        id=325,
        unique_key="job-325",
        profile_slug="scientific-ml",
        profile_label="Scientific ML + Molecular Modeling",
        search_term='"scientific machine learning"',
        source_site="linkedin",
        title="Scientific ML Scientist",
        company="MD Agent Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/325",
        description="Work on molecular simulation and machine learning potentials.",
    )
    workspace = service.ensure_workspace(job)

    with pytest.raises(
        RuntimeError,
        match="当前没有可复用的 Codex session",
    ):
        service.run_revision_advice(
            job,
            workspace,
            session_id="",
        )


def test_tailor_service_restart_runs_full_pipeline_and_bootstraps_session(tmp_path, monkeypatch) -> None:
    settings = load_settings()
    settings.app.workspaces_dir = str(tmp_path / "Role")
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    job = JobRecord(
        id=322,
        unique_key="job-322",
        profile_slug="scientific-ml",
        profile_label="Scientific ML + Molecular Modeling",
        search_term='"scientific machine learning"',
        source_site="linkedin",
        title="Scientific ML Scientist",
        company="Restart Labs",
        location_text="Chicago, IL",
        city="Chicago",
        state="IL",
        country="USA",
        job_url="https://example.com/jobs/322",
        description="Work on molecular simulation and machine learning potentials.",
    )

    workspace = service.ensure_workspace(job)

    def fake_execute_step(step_key, _job, _workspace, *, session_id, pid_callback):
        next_session_id = session_id or "session-bootstrap-123"
        return (f"{step_key} done", next_session_id)

    monkeypatch.setattr(service, "_execute_step", fake_execute_step)

    payload = service.run_pipeline_step(job, workspace, mode="restart")
    pipeline_state = service.load_pipeline_state(workspace)

    assert payload["completed"] is True
    assert payload["session_id"] == "session-bootstrap-123"
    assert pipeline_state["session_id"] == "session-bootstrap-123"
    assert pipeline_state["session_status"] == "ready"
    assert pipeline_state["session_error"] == ""
    assert pipeline_state["session_established_at"] is not None
    assert all(step["status"] == "succeeded" for step in pipeline_state["steps"])


def test_build_codex_command_uses_json_and_top_level_cd() -> None:
    settings = load_settings()
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    fresh_command = service._build_codex_command(
        session_id="",
        output_path=ROOT_DIR / "tmp-last-message.md",
    )
    resumed_command = service._build_codex_command(
        session_id="session-abc",
        output_path=ROOT_DIR / "tmp-last-message.md",
    )

    assert fresh_command[:4] == ["codex", "-C", str(ROOT_DIR), "exec"]
    assert "--json" in fresh_command
    assert resumed_command[:5] == ["codex", "-C", str(ROOT_DIR), "exec", "resume"]
    assert "--json" in resumed_command
    assert resumed_command[-2:] == ["session-abc", "-"]


def test_extract_session_id_from_codex_json() -> None:
    settings = load_settings()
    resume_profile = build_resume_profile(settings.resume_profile)
    service = TailorService(settings=settings, resume_profile=resume_profile)

    stdout_text = "\n".join(
        [
            '{"type":"session_meta","payload":{"id":"019c-session-xyz"}}',
            '{"type":"response_item","payload":{"type":"message"}}',
        ]
    )

    assert service._extract_session_id_from_codex_json(stdout_text) == "019c-session-xyz"
    assert service._extract_session_id_from_codex_json("not-json") == ""

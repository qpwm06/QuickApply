from __future__ import annotations

from app.asset_retriever import (
    AssetSection,
    _split_project_sections,
    _split_reference_entries,
    _tokenize,
    render_shortlist_markdown,
    shortlist,
    write_shortlist_for_workspace,
)


PROJECT_TEXT = """
## Projects

### Molecular Dynamics with PyTorch
- Built ML potentials for protein folding using PyTorch and OpenMM.
- Trained on AMBER trajectories for benchmarking.

### Computer Vision Image Classification
- Trained ResNet on ImageNet using PyTorch3D pipelines.
- Deployed to AWS for inference.

### LAMMPS Simulation Pipeline
- Built scientific machine learning workflows for materials science.
- Combined LAMMPS molecular dynamics with active learning.
"""

REFERENCE_TEXT = """
- Smith et al. (2024). Scientific machine learning for molecular dynamics. JACS Au, Accepted.
- Doe et al. (2023). Vision transformers for biology. Nature.
- Lee et al. (2025). LAMMPS-based active learning for materials. Science, Under Review.
"""


def test_tokenize_filters_short_and_stopwords() -> None:
    tokens = _tokenize("The PyTorch model trained on AMBER for the team.")
    assert "pytorch" in tokens
    assert "amber" in tokens
    assert "the" not in tokens
    assert "team" not in tokens


def test_split_project_sections_extracts_h3_headings() -> None:
    sections = _split_project_sections(PROJECT_TEXT)
    headings = [section.heading for section in sections]
    assert headings == [
        "Molecular Dynamics with PyTorch",
        "Computer Vision Image Classification",
        "LAMMPS Simulation Pipeline",
    ]
    assert all(isinstance(section, AssetSection) for section in sections)
    assert "PyTorch" in sections[0].body


def test_split_reference_entries_groups_bullets() -> None:
    entries = _split_reference_entries(REFERENCE_TEXT)
    assert len(entries) == 3
    assert "JACS Au" in entries[0].body
    assert entries[2].body.startswith("Lee et al.")


def test_shortlist_ranks_relevant_projects_first() -> None:
    result = shortlist(
        job_description=(
            "We are hiring a scientific machine learning scientist to work on "
            "molecular dynamics with LAMMPS and active learning for materials."
        ),
        projects_text=PROJECT_TEXT,
        reference_text=REFERENCE_TEXT,
    )
    project_headings = [section.heading for section in result["projects"]]
    assert "LAMMPS Simulation Pipeline" in project_headings
    assert project_headings[0] in {
        "LAMMPS Simulation Pipeline",
        "Molecular Dynamics with PyTorch",
    }
    reference_bodies = [section.body for section in result["references"]]
    assert any("LAMMPS" in body for body in reference_bodies)


def test_shortlist_returns_empty_when_no_signal() -> None:
    result = shortlist(
        job_description="frontend react designer",
        projects_text=PROJECT_TEXT,
        reference_text=REFERENCE_TEXT,
    )
    assert result["projects"] == []
    assert result["references"] == []


def test_render_shortlist_markdown_includes_sections() -> None:
    result = shortlist(
        job_description="scientific machine learning molecular dynamics",
        projects_text=PROJECT_TEXT,
        reference_text=REFERENCE_TEXT,
    )
    rendered = render_shortlist_markdown(result)
    assert "# Asset Shortlist" in rendered
    assert "## 推荐项目片段" in rendered
    assert "## 推荐文献片段" in rendered


def test_write_shortlist_for_workspace_writes_file(tmp_path) -> None:
    projects_path = tmp_path / "projects.md"
    reference_path = tmp_path / "reference.md"
    output_path = tmp_path / "asset_shortlist.md"
    projects_path.write_text(PROJECT_TEXT, encoding="utf-8")
    reference_path.write_text(REFERENCE_TEXT, encoding="utf-8")

    written_path = write_shortlist_for_workspace(
        job_description="scientific machine learning molecular dynamics LAMMPS",
        projects_path=projects_path,
        reference_path=reference_path,
        output_path=output_path,
    )

    assert written_path == output_path
    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert "Asset Shortlist" in text
    assert "LAMMPS" in text


def test_write_shortlist_handles_missing_files(tmp_path) -> None:
    output_path = tmp_path / "asset_shortlist.md"
    write_shortlist_for_workspace(
        job_description="anything",
        projects_path=tmp_path / "missing_projects.md",
        reference_path=tmp_path / "missing_reference.md",
        output_path=output_path,
    )
    text = output_path.read_text(encoding="utf-8")
    assert "未检索到" in text

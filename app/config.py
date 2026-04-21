from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(
    os.getenv("QUICKAPPLY_CONFIG_PATH", ROOT_DIR / "config" / "search_profiles.yaml")
)


@dataclass
class AppConfig:
    database_url: str = "sqlite:///data/jobs.db"
    refresh_interval_minutes: int = 720
    default_limit: int = 60
    default_min_score: int = 0
    min_score_to_store: int = 18
    proxy_file: str = "config/proxies.local.txt"
    workspaces_dir: str = "data/workspaces"
    codex_timeout_seconds: int = 1200


@dataclass
class ResumeProfileConfig:
    name: str
    summary: str
    source_files: list[str] = field(default_factory=list)
    target_titles: list[str] = field(default_factory=list)
    focus_domains: list[str] = field(default_factory=list)
    weighted_keywords: dict[str, float] = field(default_factory=dict)
    stop_keywords: list[str] = field(default_factory=list)


@dataclass
class SearchProfileConfig:
    slug: str
    label: str
    enabled: bool = True
    search_terms: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    sites: list[str] = field(
        default_factory=lambda: ["indeed", "linkedin", "zip_recruiter"]
    )
    results_wanted: int = 25
    hours_old: int = 168
    country_indeed: str = "USA"
    default_resume_file: str | None = None
    market_priority: float = 0.6
    search_term_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class Settings:
    app: AppConfig
    resume_profile: ResumeProfileConfig
    search_profiles: list[SearchProfileConfig] = field(default_factory=list)


def _resolve_database_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        return database_url
    if database_url == "sqlite:///:memory:":
        return database_url
    if database_url.startswith("sqlite:////"):
        return database_url

    # 中文注释：项目默认允许写相对 sqlite 路径，但不能把 :memory: 误解析成仓库里的物理文件。
    relative_path = database_url.removeprefix("sqlite:///")
    resolved_path = (ROOT_DIR / relative_path).resolve()
    return f"sqlite:///{resolved_path}"


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or Path(
        os.getenv("QUICKAPPLY_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    app = AppConfig(**(raw.get("app") or {}))
    resume_profile = ResumeProfileConfig(**(raw.get("resume_profile") or {}))
    search_profiles = [
        SearchProfileConfig(**profile_raw)
        for profile_raw in (raw.get("search_profiles") or [])
    ]
    settings = Settings(
        app=app,
        resume_profile=resume_profile,
        search_profiles=search_profiles,
    )
    settings.app.database_url = os.getenv(
        "QUICKAPPLY_DATABASE_URL",
        settings.app.database_url,
    )
    settings.app.workspaces_dir = os.getenv(
        "QUICKAPPLY_WORKSPACES_DIR",
        settings.app.workspaces_dir,
    )
    settings.app.proxy_file = os.getenv(
        "QUICKAPPLY_PROXY_FILE",
        settings.app.proxy_file,
    )
    codex_timeout = os.getenv("QUICKAPPLY_CODEX_TIMEOUT_SECONDS", "").strip()
    if codex_timeout:
        settings.app.codex_timeout_seconds = int(codex_timeout)
    settings.app.database_url = _resolve_database_url(settings.app.database_url)
    return settings


def _load_raw_config(config_path: Path | None = None) -> tuple[Path, dict]:
    path = config_path or DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return path, raw


def _normalize_search_terms(search_terms: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for item in search_terms:
        value = " ".join(str(item).split())
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_string_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = " ".join(str(item).split())
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized


def save_search_terms(
    profile_slug: str,
    search_terms: list[str],
    config_path: Path | None = None,
) -> None:
    path, raw = _load_raw_config(config_path)
    profiles = raw.get("search_profiles") or []

    for profile_raw in profiles:
        if profile_raw.get("slug") != profile_slug:
            continue
        normalized_terms = _normalize_search_terms(search_terms)
        existing_weights = {
            " ".join(str(key).split()): float(value)
            for key, value in (profile_raw.get("search_term_weights") or {}).items()
            if " ".join(str(key).split())
        }
        profile_raw["search_terms"] = normalized_terms
        profile_raw["search_term_weights"] = {
            term: existing_weights.get(term, 1.0)
            for term in normalized_terms
        }
        path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return

    raise KeyError(f"profile not found: {profile_slug}")


def save_profile_locations(
    profile_slug: str,
    locations: list[str],
    config_path: Path | None = None,
) -> None:
    path, raw = _load_raw_config(config_path)
    profiles = raw.get("search_profiles") or []

    for profile_raw in profiles:
        if profile_raw.get("slug") != profile_slug:
            continue
        profile_raw["locations"] = _normalize_string_list(locations) or ["United States"]
        path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return

    raise KeyError(f"profile not found: {profile_slug}")


def add_search_profile(
    *,
    label: str,
    slug: str = "",
    search_terms: list[str] | None = None,
    locations: list[str] | None = None,
    sites: list[str] | None = None,
    default_resume_file: str | None = None,
    config_path: Path | None = None,
) -> str:
    path, raw = _load_raw_config(config_path)
    profiles = raw.setdefault("search_profiles", [])

    normalized_label = " ".join(label.split())
    resolved_slug = _slugify(slug or normalized_label)
    if not normalized_label:
        raise ValueError("label is required")
    if not resolved_slug:
        raise ValueError("slug is required")
    if any((profile_raw.get("slug") or "").strip() == resolved_slug for profile_raw in profiles):
        raise ValueError(f"profile already exists: {resolved_slug}")

    normalized_terms = _normalize_search_terms(list(search_terms or []))
    normalized_locations = _normalize_string_list(list(locations or [])) or ["United States"]
    normalized_sites = [
        site for site in _normalize_string_list(list(sites or []))
        if site in {"linkedin", "indeed", "zip_recruiter"}
    ] or ["linkedin", "indeed"]

    profiles.append(
        {
            "slug": resolved_slug,
            "label": normalized_label,
            "enabled": True,
            "default_resume_file": " ".join((default_resume_file or "").split()),
            "search_terms": normalized_terms,
            "search_term_weights": {
                term: 1.0 for term in normalized_terms
            },
            "locations": normalized_locations,
            "sites": normalized_sites,
            "results_wanted": 25,
            "hours_old": 168,
            "country_indeed": "USA",
            "market_priority": 0.6,
        }
    )
    path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return resolved_slug


def delete_search_profile(
    profile_slug: str,
    config_path: Path | None = None,
) -> None:
    path, raw = _load_raw_config(config_path)
    profiles = raw.get("search_profiles") or []
    updated_profiles = [
        profile_raw for profile_raw in profiles
        if profile_raw.get("slug") != profile_slug
    ]
    if len(updated_profiles) == len(profiles):
        raise KeyError(f"profile not found: {profile_slug}")
    raw["search_profiles"] = updated_profiles
    path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

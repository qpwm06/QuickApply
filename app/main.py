import atexit
import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import bleach
import markdown
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from app.config import (
    ROOT_DIR,
    add_search_profile,
    delete_search_profile,
    load_settings,
    save_profile_locations,
    save_search_terms,
)
from app.fetcher import JobSpyFetcher
from app.location_utils import (
    COUNTRY_FILTER_OPTIONS,
    job_country_label,
    linkedin_jobs_search_url,
    normalize_selected_countries,
    source_site_home_url,
)
from app.models import ApplicationTrack, TailorRun
from app.resume_profile import build_resume_profile
from app.scheduler import build_scheduler
from app.scoring import (
    DOMAIN_WEIGHT,
    KEYWORD_WEIGHT,
    MARKET_WEIGHT,
    STOP_KEYWORD_PENALTY,
    TITLE_WEIGHT,
)
from app.service import JobMonitorService
from app.storage import JobRepository
from app.tailor_service import TAILOR_STEP_LABELS, TailorService, split_revision_advice
from app.time_utils import LOCAL_TIMEZONE, LOCAL_TIMEZONE_LABEL, format_local_time

TRACK_STAGE_OPTIONS = ("submitted", "introduced", "interviewed", "paneled", "failed")
TRACK_STAGE_LABELS = {
    "submitted": "Submitted",
    "introduced": "Introduced",
    "interviewed": "Interviewed",
    "paneled": "Paneled",
    "failed": "Failed",
}
TRACKER_CHART_RANGE_LABELS = {
    "all": "总时间",
    "7d": "7 日",
    "month": "本月",
    "30d": "30 日",
}
TRACKER_CHART_SERIES = (
    {"key": "applied", "label": "投递", "color": "#14b8a6"},
    {"key": "crawled", "label": "爬取", "color": "#0ea5e9"},
    {"key": "reviewed", "label": "已查阅", "color": "#f59e0b"},
    {"key": "dismissed", "label": "不合适", "color": "#f97316"},
)
TRACKER_CHART_DEFAULT_VISIBLE_SERIES = ("applied",)
ACTIVE_RUN_STATUSES = {"pending", "running"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "stopped"}
AD_HOC_STEP_LABELS = {
    "advice": "Advice",
    "revision_advice": "Revision Advice",
    "session_start": "Session Start",
    "session_prompt": "Session Prompt",
    "final_prompt": "Final Prompt",
}
MARKDOWN_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
MARKDOWN_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "code": ["class"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}
BROWSER_WINDOW_STATE_FILENAME = "chrome_job_window_state.json"
JOB_BROWSER_WINDOW_MARKER_TITLE = "QuickApply Browser Window Marker"
JOB_BROWSER_WINDOW_MARKER_TEXT = "This tab marks the dedicated Chrome job browser window."


@dataclass(frozen=True)
class BrowserWindowOpenResult:
    window_id: str
    warning: str = ""


def browser_window_state_path(database_url: str) -> Path:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        sqlite_path = Path(database_url.removeprefix("sqlite:///"))
        return sqlite_path.resolve().parent / BROWSER_WINDOW_STATE_FILENAME
    return ROOT_DIR / "data" / BROWSER_WINDOW_STATE_FILENAME


def load_browser_window_state(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "window_id": str(payload.get("window_id") or "").strip(),
        "marker_url": str(payload.get("marker_url") or "").strip(),
        "updated_at": str(payload.get("updated_at") or "").strip(),
    }


def save_browser_window_state(state_path: Path, *, window_id: str, marker_url: str) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "window_id": window_id,
                "marker_url": marker_url,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_browser_window_state(state_path: Path) -> None:
    try:
        state_path.unlink(missing_ok=True)
    except OSError:
        return


def subprocess_failure_detail(exc: subprocess.CalledProcessError) -> str:
    detail = " ".join(((exc.stderr or exc.stdout or "").strip()).split())
    return detail[:240]


def chrome_site_behavior_for_url(target_url: str) -> str:
    hostname = (urlsplit(target_url).hostname or "").strip().lower()
    if hostname.endswith("linkedin.com"):
        return "linkedin_auto_expand"
    return "default"


def linkedin_expand_javascript() -> str:
    return """
(() => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const targetPhrases = [
    'show more',
    'see more',
    '...more',
    '…more',
    'show all',
    'read more',
    'expand',
    '显示更多',
    '查看全部',
    '展开',
  ];
  const candidateSelectors = [
    'button',
    'a',
    '[role="button"]',
    '.jobs-description__footer-button',
    '.show-more-less-html__button',
    '.artdeco-card__actions button',
  ];

  const seen = new Set();
  const isVisible = (node) => {
    if (!(node instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const collectText = (node) =>
    normalize(
      [
        node.innerText,
        node.textContent,
        node.getAttribute?.('aria-label'),
        node.getAttribute?.('title'),
      ]
        .filter(Boolean)
        .join(' '),
    );

  let clicked = 0;
  const candidates = [...new Set(candidateSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector))))];
  for (const node of candidates) {
    if (!(node instanceof HTMLElement) || seen.has(node) || !isVisible(node)) continue;
    if (node.getAttribute('aria-expanded') === 'true') continue;
    const text = collectText(node);
    if (!text) continue;
    if (!targetPhrases.some((phrase) => text === phrase || text.startsWith(phrase) || text.includes(phrase))) {
      continue;
    }
    seen.add(node);
    node.click();
    clicked += 1;
  }

  for (const node of document.querySelectorAll('.jobs-box__html-content, .show-more-less-html__markup, .jobs-description__container, .jobs-description-content__text, .jobs-description-details__list')) {
    if (!(node instanceof HTMLElement)) continue;
    node.style.maxHeight = 'none';
    node.style.height = 'auto';
    node.style.overflow = 'visible';
    node.style.webkitLineClamp = 'unset';
  }

  return clicked;
})();
""".strip()


def open_url_in_dedicated_chrome_window(
    target_url: str,
    *,
    state_path: Path,
    marker_url: str,
    site_behavior: str = "default",
) -> BrowserWindowOpenResult:
    previous_state = load_browser_window_state(state_path)
    previous_window_id = previous_state.get("window_id", "")
    previous_marker_url = previous_state.get("marker_url", "")
    if previous_marker_url and previous_marker_url != marker_url:
        previous_window_id = ""

    # 中文注释：岗位窗口和 LinkedIn 展开拆成两步。先确保窗口稳定打开，再做 best-effort 展开，
    # 避免“窗口其实已经打开，但因为展开脚本报错而整体返回失败”。
    applescript = """
on run argv
  set targetUrl to item 1 of argv
  set existingWindowId to item 2 of argv
  set markerUrl to item 3 of argv
  set siteBehavior to item 4 of argv

  tell application "Finder"
    set screenBounds to bounds of window of desktop
  end tell

  set leftEdge to item 1 of screenBounds
  set topEdge to item 2 of screenBounds
  set rightEdge to item 3 of screenBounds
  set bottomEdge to item 4 of screenBounds
  set screenWidth to rightEdge - leftEdge
  set screenHeight to bottomEdge - topEdge

  set widthRatio to 0.42
  if siteBehavior is "linkedin_auto_expand" then
    set widthRatio to 0.68
  end if
  set targetWidth to round (screenWidth * widthRatio)
  if targetWidth < 560 then set targetWidth to 560
  set targetHeight to screenHeight - 48
  if targetHeight < 720 then set targetHeight to 720
  if targetHeight > screenHeight then set targetHeight to screenHeight

  set targetLeft to rightEdge - targetWidth - 16
  if targetLeft < leftEdge then set targetLeft to leftEdge
  set targetTop to topEdge + 24
  if targetTop < topEdge then set targetTop to topEdge

  set targetRight to targetLeft + targetWidth
  if targetRight > rightEdge then set targetRight to rightEdge
  set targetBottom to targetTop + targetHeight
  if targetBottom > bottomEdge then set targetBottom to bottomEdge

  tell application "Google Chrome"
    activate
    set targetWindow to missing value
    set createdNewWindow to false

    if existingWindowId is not "" then
      set targetWindow to my findWindowById(existingWindowId)
      if targetWindow is not missing value then
        if my windowHasMarkerTab(targetWindow, markerUrl) is false then
          set targetWindow to missing value
        end if
      end if
    end if

    if targetWindow is missing value then
      set targetWindow to my findWindowByMarker(markerUrl)
    end if

    if targetWindow is missing value then
      make new window
      set targetWindow to front window
      set createdNewWindow to true
    end if

    if createdNewWindow then
      set bounds of targetWindow to {targetLeft, targetTop, targetRight, targetBottom}
    end if

    set markerTabIndex to my findTabIndexByUrl(targetWindow, markerUrl)
    if markerTabIndex is 0 then
      set markerTabIndex to 1
      set URL of tab markerTabIndex of targetWindow to markerUrl
      my waitForTabLoad(tab markerTabIndex of targetWindow, 40)
    end if

    set targetTabIndex to my firstNonMarkerTabIndex(targetWindow, markerUrl)
    if targetTabIndex is 0 then
      tell targetWindow to make new tab at end of tabs
      set targetTabIndex to count of tabs of targetWindow
    end if

    set URL of tab targetTabIndex of targetWindow to targetUrl
    set active tab index of targetWindow to targetTabIndex
    set index of targetWindow to 1
    my waitForTabLoad(tab targetTabIndex of targetWindow, 80)

    return (id of targetWindow as text)
  end tell
end run

on findWindowById(existingWindowId)
  tell application "Google Chrome"
    repeat with w in windows
      if (id of w as text) = existingWindowId then
        return w
      end if
    end repeat
  end tell
  return missing value
end findWindowById

on findTabIndexByUrl(targetWindow, expectedUrl)
  tell application "Google Chrome"
    set tabCount to count of tabs of targetWindow
    repeat with tabIndex from 1 to tabCount
      try
        if (URL of tab tabIndex of targetWindow as text) is expectedUrl then
          return tabIndex
        end if
      end try
    end repeat
  end tell
  return 0
end findTabIndexByUrl

on windowHasMarkerTab(targetWindow, markerUrl)
  return (my findTabIndexByUrl(targetWindow, markerUrl)) is not 0
end windowHasMarkerTab

on findWindowByMarker(markerUrl)
  tell application "Google Chrome"
    repeat with w in windows
      if my windowHasMarkerTab(w, markerUrl) then
        return w
      end if
    end repeat
  end tell
  return missing value
end findWindowByMarker

on firstNonMarkerTabIndex(targetWindow, markerUrl)
  tell application "Google Chrome"
    set tabCount to count of tabs of targetWindow
    repeat with tabIndex from 1 to tabCount
      try
        if (URL of tab tabIndex of targetWindow as text) is not markerUrl then
          return tabIndex
        end if
      on error
        return tabIndex
      end try
    end repeat
  end tell
  return 0
end firstNonMarkerTabIndex

on waitForTabLoad(targetTab, maxAttempts)
  repeat with attempt from 1 to maxAttempts
    try
      tell application "Google Chrome"
        if loading of targetTab is false then exit repeat
      end tell
    end try
    delay 0.25
  end repeat
end waitForTabLoad
""".strip()
    result = subprocess.run(
        [
            "osascript",
            "-e",
            applescript,
            target_url,
            previous_window_id,
            marker_url,
            site_behavior,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    next_window_id = (result.stdout or "").strip()
    if not next_window_id:
        raise RuntimeError("Chrome 窗口控制没有返回 window id。")
    save_browser_window_state(state_path, window_id=next_window_id, marker_url=marker_url)

    warning = ""
    if site_behavior == "linkedin_auto_expand":
        warning = best_effort_expand_linkedin_window(next_window_id)

    return BrowserWindowOpenResult(window_id=next_window_id, warning=warning)


def best_effort_expand_linkedin_window(window_id: str) -> str:
    expand_javascript = linkedin_expand_javascript()
    applescript = """
on run argv
  set existingWindowId to item 1 of argv
  set expandJavascript to item 2 of argv

  tell application "Google Chrome"
    set targetWindow to my findWindowById(existingWindowId)
    if targetWindow is missing value then error "找不到专用岗位窗口。"

    set targetTabIndex to active tab index of targetWindow
    set targetTab to tab targetTabIndex of targetWindow
    my waitForTabLoad(targetTab, 80)
    delay 0.4
    my runExpandJavascript(targetTab, expandJavascript)
    delay 1.0
    my runExpandJavascript(targetTab, expandJavascript)
  end tell

  return ""
end run

on findWindowById(existingWindowId)
  tell application "Google Chrome"
    repeat with w in windows
      if (id of w as text) = existingWindowId then
        return w
      end if
    end repeat
  end tell
  return missing value
end findWindowById

on waitForTabLoad(targetTab, maxAttempts)
  repeat with attempt from 1 to maxAttempts
    try
      tell application "Google Chrome"
        if loading of targetTab is false then exit repeat
      end tell
    end try
    delay 0.25
  end repeat
end waitForTabLoad

on runExpandJavascript(targetTab, expandJavascript)
  tell application "Google Chrome"
    execute targetTab javascript expandJavascript
  end tell
end runExpandJavascript
""".strip()
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                applescript,
                window_id,
                expand_javascript,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = subprocess_failure_detail(exc)
        if detail:
            return f"LinkedIn 自动展开附加步骤失败：{detail}"
        return "LinkedIn 自动展开附加步骤失败。"
    return ""


def render_markdown_html(text: str) -> str:
    source = (text or "").strip()
    if not source:
        return ""
    rendered = markdown.markdown(
        source,
        extensions=["extra", "fenced_code", "sane_lists", "tables", "nl2br"],
        output_format="html5",
    )
    return bleach.clean(
        rendered,
        tags=MARKDOWN_ALLOWED_TAGS,
        attributes=MARKDOWN_ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def create_app() -> Flask:
    web_app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / "templates"),
        static_folder=str(ROOT_DIR / "static"),
    )
    settings = load_settings()
    repository = JobRepository(settings.app.database_url)
    repository.init_db()

    def rebuild_runtime_state() -> None:
        settings = load_settings()
        resume_profile = build_resume_profile(settings.resume_profile)
        repository.sync_profile_labels(
            {profile.slug: profile.label for profile in settings.search_profiles}
        )
        service = JobMonitorService(
            settings=settings,
            resume_profile=resume_profile,
            repository=repository,
            fetcher=JobSpyFetcher(proxy_file=settings.app.proxy_file),
        )
        tailor_service = TailorService(settings=settings, resume_profile=resume_profile)
        web_app.config["settings"] = settings
        web_app.config["service"] = service
        web_app.config["resume_profile"] = resume_profile
        web_app.config["tailor_service"] = tailor_service
        web_app.config["browser_window_state_path"] = browser_window_state_path(
            settings.app.database_url
        )

    rebuild_runtime_state()
    web_app.config["repository"] = repository
    web_app.config["local_timezone_label"] = LOCAL_TIMEZONE_LABEL
    web_app.config["refresh_lock"] = threading.Lock()
    web_app.config["refresh_state"] = {
        "running": False,
        "profile_slug": "",
        "profile_label": "",
        "started_at": None,
        "finished_at": None,
        "last_result": "",
        "last_trigger": "",
    }
    web_app.jinja_env.globals["local_timezone_label"] = LOCAL_TIMEZONE_LABEL
    web_app.jinja_env.globals["source_site_home_url"] = source_site_home_url
    web_app.jinja_env.globals["linkedin_jobs_search_url"] = linkedin_jobs_search_url

    @web_app.template_filter("localtime")
    def localtime_filter(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
        return format_local_time(value, fmt)

    def get_profile_label(profile_slug: str) -> str:
        if profile_slug == "all":
            return "全部画像"
        service = web_app.config["service"]
        for profile in service.enabled_profiles():
            if profile.slug == profile_slug:
                return profile.label
        return profile_slug

    def get_step_label(step_key: str) -> str:
        return TAILOR_STEP_LABELS.get(step_key, AD_HOC_STEP_LABELS.get(step_key, step_key))

    def is_async_request() -> bool:
        accept = request.headers.get("Accept", "")
        requested_with = request.headers.get("X-Requested-With", "")
        return "application/json" in accept or requested_with == "quickapply"

    def json_message(message: str, *, payload: dict[str, object] | None = None, status: int = 200):
        response_payload = {"ok": status < 400, "message": message}
        if payload:
            response_payload.update(payload)
        return jsonify(response_payload), status

    def build_scoring_model() -> dict[str, object]:
        resume_profile = web_app.config["resume_profile"]
        return {
            "formula": (
                "总分 = 0.45 × 标题相似度 + 0.30 × 关键词覆盖 + 0.15 × 领域相似度"
                " + 0.10 × 市场供给匹配"
                f" - {STOP_KEYWORD_PENALTY:.2f} × stop-keyword 命中"
            ),
            "title_weight": TITLE_WEIGHT,
            "keyword_weight": KEYWORD_WEIGHT,
            "domain_weight": DOMAIN_WEIGHT,
            "market_weight": MARKET_WEIGHT,
            "penalty": STOP_KEYWORD_PENALTY,
            "keywords": sorted(
                resume_profile.weighted_keywords.items(),
                key=lambda item: item[1],
                reverse=True,
            ),
        }

    def build_profiles_view() -> list[dict[str, object]]:
        service = web_app.config["service"]
        profile_stats = {
            item["profile_slug"]: item
            for item in repository.profile_stats()
        }
        profiles_view: list[dict[str, object]] = []
        for profile in service.enabled_profiles():
            linkedin_location = next(
                (location for location in profile.locations if location and location.lower() != "remote"),
                profile.locations[0] if profile.locations else "",
            )
            stat = profile_stats.get(
                profile.slug,
                {
                    "job_count": 0,
                    "best_score": 0.0,
                    "last_refresh": None,
                    "source_sites": [],
                },
            )
            profiles_view.append(
                {
                    "profile": profile,
                    "job_count": stat["job_count"],
                    "best_score": stat["best_score"],
                    "last_refresh": stat["last_refresh"],
                    "source_sites": stat["source_sites"],
                    "linkedin_location": linkedin_location,
                    "market_priority": profile.market_priority,
                    "market_tier": (
                        "主池"
                        if profile.market_priority >= 0.85
                        else "桥接池"
                        if profile.market_priority >= 0.65
                        else "卫星池"
                    ),
                    "term_weights": [
                        {
                            "term": term,
                            "weight": float((profile.search_term_weights or {}).get(term, 1.0)),
                        }
                        for term in profile.search_terms
                    ],
                }
            )
        return profiles_view

    def build_refresh_run_view(run) -> dict[str, object]:
        result = repository.decode_refresh_result(run)
        raw_warnings = result.get("warnings", []) if isinstance(result, dict) else []
        warnings = [
            str(item).strip()
            for item in raw_warnings
            if str(item).strip()
        ] if isinstance(raw_warnings, list) else []
        if not warnings and run.warnings_text.strip():
            warnings = [
                line.strip()
                for line in run.warnings_text.splitlines()
                if line.strip()
            ]

        raw_query_details = result.get("query_details", []) if isinstance(result, dict) else []
        query_details = [
            {
                "search_term": str(item.get("search_term") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "requested_sites": [
                    str(site).strip()
                    for site in (item.get("requested_sites") or [])
                    if str(site).strip()
                ],
                "sites_seen": [
                    str(site).strip()
                    for site in (item.get("sites_seen") or [])
                    if str(site).strip()
                ],
                "row_count": int(item.get("row_count") or 0),
                "status": str(item.get("status") or "unknown"),
                "error": str(item.get("error") or "").strip(),
            }
            for item in raw_query_details
            if isinstance(item, dict)
        ] if isinstance(raw_query_details, list) else []

        return {
            "run": run,
            "result": result,
            "warnings": warnings,
            "query_details": query_details,
            "requested_sites": [
                str(site).strip()
                for site in ((result.get("requested_sites") or []) if isinstance(result, dict) else [])
                if str(site).strip()
            ],
        }

    def split_multiline_input(raw_value: str) -> list[str]:
        values: list[str] = []
        for chunk in raw_value.replace("|", "\n").replace(",", "\n").splitlines():
            normalized = " ".join(chunk.split())
            if normalized:
                values.append(normalized)
        return values

    def split_location_input(raw_value: str) -> list[str]:
        values: list[str] = []
        for chunk in raw_value.replace("|", "\n").splitlines():
            normalized = " ".join(chunk.split())
            if normalized:
                values.append(normalized)
        return values

    def build_jobs_view(
        *,
        profile_slug: str | None = None,
        min_score: float = 0.0,
        limit: int = 60,
        countries: list[str] | None = None,
        location_query: str = "",
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        recent_hours: int = 0,
        sort_by: str = "recent",
    ) -> list[dict[str, object]]:
        jobs = repository.list_jobs(
            profile_slug=profile_slug,
            min_score=min_score,
            limit=limit,
            countries=countries,
            location_query=location_query,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            recent_hours=recent_hours,
            sort_by=sort_by,
        )
        return [
            {
                "job": job,
                "country_label": job_country_label(job),
            }
            for job in jobs
        ]

    def build_tailor_run_view_item(item: dict[str, object]) -> dict[str, object]:
        run = item["run"]
        job = item["job"]
        result = item["result"]
        step_records = item["steps"]
        if isinstance(result, dict) and result.get("steps"):
            steps = result.get("steps", [])
        else:
            steps = [
                {"key": step.step_key, "label": get_step_label(step.step_key), "status": step.status}
                for step in step_records
            ]
        current_step_key = (
            run.current_step_key
            or (str(result.get("current_step") or "") if isinstance(result, dict) else "")
        )
        current_step_label = get_step_label(current_step_key)
        completed_steps = 0
        for step in steps:
            if step.get("status") == "succeeded":
                completed_steps += 1
            elif not current_step_label:
                current_step_label = str(step.get("label") or "")
        if not current_step_label and steps:
            current_step_label = str(steps[-1].get("label") or "")
        if not current_step_label:
            current_step_label = "尚未开始"
        artifacts = result.get("artifacts", {}) if isinstance(result, dict) else {}
        final_pdf_name = str(artifacts.get("final_pdf") or "")
        final_pdf_ready = False
        if run.workspace_dir:
            workspace_dir = Path(run.workspace_dir)
            if final_pdf_name:
                final_pdf_ready = (workspace_dir / final_pdf_name).exists()
            else:
                final_pdf_ready = (workspace_dir / "final_resume.pdf").exists() or any(
                    workspace_dir.glob("cv-*.pdf")
                )
        return {
            "run": run,
            "job": job,
            "result": result,
            "step_records": step_records,
            "workspace_label": Path(run.workspace_dir).name if run.workspace_dir else "",
            "job_country": job_country_label(job) if job is not None else "Unknown",
            "current_step_label": current_step_label or "已完成",
            "completed_steps": completed_steps,
            "session_id": run.session_id or str(result.get("session_id") or ""),
            "base_resume_name": Path(run.base_resume_path).name if run.base_resume_path else "",
            "final_pdf_ready": final_pdf_ready,
            "latest_message": run.last_message or run.error_text,
        }

    def build_tailor_run_views(
        *,
        status: str | None = None,
        profile_slug: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, object]]:
        items = repository.list_tailor_runs(
            status=status,
            profile_slug=profile_slug,
            limit=limit,
        )
        return [build_tailor_run_view_item(item) for item in items]

    def build_tailor_workspace_views_from_items(
        items: list[dict[str, object]],
        *,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        grouped: dict[str, dict[str, object]] = {}
        ordered_views: list[dict[str, object]] = []
        for item in items:
            run_view = build_tailor_run_view_item(item)
            run = run_view["run"]
            workspace_key = str(run.workspace_dir or f"job:{run.job_id}")
            existing = grouped.get(workspace_key)
            if existing is None:
                workspace_view = {
                    **run_view,
                    "workspace_key": workspace_key,
                    "run_count": 1,
                    "latest_run_id": run.id,
                    "latest_status": run.status,
                    "latest_updated_at": run.updated_at,
                    "active_run_id": run.id if run.status in ACTIVE_RUN_STATUSES else None,
                }
                grouped[workspace_key] = workspace_view
                ordered_views.append(workspace_view)
                continue

            existing["run_count"] = int(existing["run_count"]) + 1
            if not existing.get("job") and run_view.get("job") is not None:
                existing["job"] = run_view["job"]
                existing["job_country"] = run_view["job_country"]
            if not existing.get("base_resume_name") and run_view.get("base_resume_name"):
                existing["base_resume_name"] = run_view["base_resume_name"]
            if existing.get("active_run_id") is None and run.status in ACTIVE_RUN_STATUSES:
                existing["active_run_id"] = run.id
        if limit is None:
            return ordered_views
        return ordered_views[:limit]

    def build_tailor_workspace_views(
        *,
        status: str | None = None,
        profile_slug: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, object]]:
        fetch_limit = max(limit * 8, 120)
        items = repository.list_tailor_runs(
            status=status,
            profile_slug=profile_slug,
            limit=fetch_limit,
        )
        return build_tailor_workspace_views_from_items(items, limit=limit)

    def build_tailor_history_views_for_job(job, *, limit: int = 6, count_limit: int = 200):
        runs = repository.list_tailor_runs_for_job(job.id or 0, limit=count_limit)
        items = [
            {
                "run": run,
                "job": job,
                "result": repository.decode_tailor_result(run),
                "steps": repository.list_tailor_run_steps(run.id or 0),
            }
            for run in runs
        ]
        run_views = [build_tailor_run_view_item(item) for item in items]
        summary = None
        if run_views:
            latest_view = run_views[0]
            summary = {
                "workspace_label": latest_view["workspace_label"],
                "run_count": len(runs),
                "latest_status": latest_view["run"].status,
                "latest_step_label": latest_view["current_step_label"],
                "latest_updated_at": latest_view["run"].updated_at.isoformat()
                if latest_view["run"].updated_at
                else None,
                "latest_session_id": latest_view["session_id"],
                "latest_message": latest_view["latest_message"],
                "base_resume_name": latest_view["base_resume_name"],
            }
        history = [
            {
                "id": view["run"].id,
                "status": view["run"].status,
                "step_key": view["run"].current_step_key,
                "step_label": view["current_step_label"],
                "updated_at": view["run"].updated_at.isoformat() if view["run"].updated_at else None,
                "session_id": view["session_id"],
                "last_message": view["latest_message"],
                "base_resume_name": view["base_resume_name"],
            }
            for view in run_views[:limit]
        ]
        return summary, history

    def build_application_track_views(
        *,
        source_kind: str | None = None,
        keyword: str | None = None,
        stage: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        items = repository.list_application_tracks(
            source_kind=source_kind,
            keyword=keyword,
            stage=stage,
            limit=limit,
        )
        views: list[dict[str, object]] = []
        for item in items:
            track = item["track"]
            job = item["job"]
            events = item.get("events", [])
            views.append(
                {
                    "track": track,
                    "job": job,
                    "events": events,
                    "track_kind_label": "关联职位" if track.source_kind == "linked" else "手工录入",
                    "job_country": job_country_label(job) if job is not None else "Unknown",
                    "current_stage_label": TRACK_STAGE_LABELS.get(track.current_stage, track.current_stage),
                }
            )
        return views

    def build_application_track_chart_view(*, range_key: str) -> dict[str, object]:
        chart_data = repository.application_track_daily_counts(
            range_key=range_key,
            reference_time=datetime.now(timezone.utc),
        )
        svg_height = 320
        plot_top = 18
        plot_bottom = 42
        plot_left = 46
        plot_right = 22
        plot_height = svg_height - plot_top - plot_bottom
        plot_base_y = plot_top + plot_height
        grid_step_count = 4
        chart_view = {
            "range_key": chart_data["range_key"],
            "has_data": chart_data["has_data"],
            "series": [
                {
                    **series_meta,
                    "total": int(chart_data["totals"].get(series_meta["key"], 0)),
                    "default_visible": series_meta["key"] in TRACKER_CHART_DEFAULT_VISIBLE_SERIES,
                    "bars": [],
                }
                for series_meta in TRACKER_CHART_SERIES
            ],
            "grid_lines": [],
            "x_labels": [],
            "svg_width": 960,
            "svg_height": svg_height,
            "default_visible_keys": list(TRACKER_CHART_DEFAULT_VISIBLE_SERIES),
            "max_value": 0,
            "plot_top": plot_top,
            "plot_height": plot_height,
            "plot_base_y": plot_base_y,
            "grid_step_count": grid_step_count,
            "client_payload": {
                "labels": list(chart_data["labels"]),
                "series": {
                    series_meta["key"]: list(chart_data["series"].get(series_meta["key"], []))
                    for series_meta in TRACKER_CHART_SERIES
                },
                "plot_top": plot_top,
                "plot_height": plot_height,
                "plot_base_y": plot_base_y,
                "grid_step_count": grid_step_count,
            },
        }
        if not chart_data["has_data"]:
            return chart_view

        label_values = chart_data["labels"]
        day_count = len(label_values)
        if day_count <= 7:
            group_step = 78
        elif day_count <= 14:
            group_step = 54
        elif day_count <= 31:
            group_step = 34
        elif day_count <= 90:
            group_step = 22
        else:
            group_step = 14

        svg_width = max(960, plot_left + plot_right + day_count * group_step)
        series_count = len(TRACKER_CHART_SERIES)
        bar_gap = 2
        group_width = max(14, group_step - 8)
        bar_width = max(2, min(12, int((group_width - bar_gap * (series_count - 1)) / series_count)))
        used_width = bar_width * series_count + bar_gap * (series_count - 1)
        group_offset = max(0, (group_step - used_width) / 2)
        default_visible_max = max(
            (
                max(chart_data["series"].get(series_key, []), default=0)
                for series_key in TRACKER_CHART_DEFAULT_VISIBLE_SERIES
            ),
            default=0,
        )
        max_value = max(int(default_visible_max or chart_data["max_value"]), 1)

        chart_view["svg_width"] = int(svg_width)
        chart_view["svg_height"] = svg_height
        chart_view["max_value"] = max_value
        chart_view["grid_lines"] = [
            {
                "value": int(round(max_value * index / grid_step_count)),
                "y": plot_top + plot_height - (plot_height * index / grid_step_count),
            }
            for index in range(grid_step_count + 1)
        ]

        if day_count <= 10:
            label_stride = 1
        elif day_count <= 20:
            label_stride = 2
        elif day_count <= 40:
            label_stride = 4
        elif day_count <= 90:
            label_stride = 7
        else:
            label_stride = 14

        for index, label in enumerate(label_values):
            center_x = plot_left + index * group_step + group_step / 2
            if index % label_stride == 0 or index == day_count - 1:
                chart_view["x_labels"].append(
                    {
                        "x": center_x,
                        "short_label": label[5:],
                        "full_label": label,
                    }
                )

        series_by_key = {item["key"]: item for item in chart_view["series"]}
        for series_index, series_meta in enumerate(TRACKER_CHART_SERIES):
            key = series_meta["key"]
            counts = chart_data["series"].get(key, [])
            series_view = series_by_key[key]
            for day_index, value in enumerate(counts):
                if value <= 0:
                    continue
                bar_height = plot_height * value / max_value
                if 0 < bar_height < 2:
                    bar_height = 2
                x = plot_left + day_index * group_step + group_offset + series_index * (bar_width + bar_gap)
                y = plot_base_y - bar_height
                series_view["bars"].append(
                    {
                        "x": round(x, 2),
                        "y": round(y, 2),
                        "width": bar_width,
                        "height": round(bar_height, 2),
                        "label": label_values[day_index],
                        "value": value,
                    }
                )
        return chart_view

    def parse_local_datetime_input(raw_value: str) -> datetime:
        # 中文注释：`datetime-local` 不带时区，统一按芝加哥时间解释，再转成 UTC 入库。
        parsed = datetime.fromisoformat(raw_value.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
        return parsed.astimezone(timezone.utc)

    def build_shell_context(
        *,
        current_page: str,
        page_title: str,
        page_subtitle: str,
        page_sections: list[dict[str, str]],
        page_eyebrow: str,
        message: str = "",
        page_badges: list[str] | None = None,
        page_actions: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        refresh_state = web_app.config["refresh_state"]
        app_nav = [
            {"id": "dashboard", "label": "Dashboard", "href": url_for("dashboard"), "short": "DB"},
            {"id": "crawler", "label": "Crawler", "href": url_for("crawler"), "short": "CR"},
            {"id": "jobs", "label": "Jobs", "href": url_for("jobs_page"), "short": "JB"},
            {
                "id": "application_tracker",
                "label": "Tracker",
                "href": url_for("application_tracker"),
                "short": "TR",
            },
            {
                "id": "tailor_tasks",
                "label": "Tailor",
                "href": url_for("tailor_tasks"),
                "short": "TL",
            },
        ]
        return {
            "app_nav": app_nav,
            "current_page": current_page,
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "page_sections": page_sections,
            "page_eyebrow": page_eyebrow,
            "page_badges": page_badges or [],
            "page_actions": page_actions or [],
            "message": message,
            "refresh_state": refresh_state,
        }

    def resolve_redirect_endpoint(raw_endpoint: str | None, default: str = "crawler") -> str:
        allowed = {"dashboard", "crawler", "jobs_page", "application_tracker", "tailor_tasks"}
        if raw_endpoint in allowed:
            return raw_endpoint
        return default

    def strip_message_query(path_with_query: str) -> str:
        parsed = urlsplit(path_with_query)
        clean_query = urlencode(
            [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "message"],
            doseq=True,
        )
        return urlunsplit(("", "", parsed.path, clean_query, ""))

    def current_run_step_label(run, runtime_step_label: str) -> str:
        if run is not None and run.status in ACTIVE_RUN_STATUSES and run.current_step_key:
            return get_step_label(run.current_step_key)
        return runtime_step_label

    def run_refresh_task(profile_slug: str, trigger: str) -> None:
        refresh_state = web_app.config["refresh_state"]
        service = web_app.config["service"]

        try:
            if profile_slug == "all":
                outcomes = service.refresh_all()
                summary = (
                    f"刷新完成：{len(outcomes)} 个画像，"
                    f"合计保存 {sum(item.jobs_saved for item in outcomes)} 条职位。"
                )
            else:
                outcome = service.refresh_profile(profile_slug)
                summary = (
                    f"画像 {outcome.profile_label} 刷新完成：抓到 {outcome.jobs_seen} 条，"
                    f"保存 {outcome.jobs_saved} 条。"
                )
        except Exception as exc:
            summary = f"刷新失败：{exc}"
        finally:
            with web_app.config["refresh_lock"]:
                refresh_state["running"] = False
                refresh_state["finished_at"] = datetime.now(timezone.utc)
                refresh_state["last_result"] = summary
                refresh_state["last_trigger"] = trigger

    def launch_refresh(profile_slug: str, trigger: str) -> tuple[bool, str]:
        refresh_state = web_app.config["refresh_state"]
        profile_label = get_profile_label(profile_slug)

        with web_app.config["refresh_lock"]:
            if refresh_state["running"]:
                started_at = refresh_state["started_at"]
                started_text = (
                    format_local_time(started_at, "%Y-%m-%d %H:%M:%S %Z")
                    if started_at
                    else "未知时间"
                )
                return (
                    False,
                    f"已有刷新任务在运行：{refresh_state['profile_label']}，开始于 {started_text}。",
                )

            refresh_state["running"] = True
            refresh_state["profile_slug"] = profile_slug
            refresh_state["profile_label"] = profile_label
            refresh_state["started_at"] = datetime.now(timezone.utc)
            refresh_state["finished_at"] = None
            refresh_state["last_trigger"] = trigger

        worker = threading.Thread(
            target=run_refresh_task,
            args=(profile_slug, trigger),
            daemon=True,
            name=f"refresh-{profile_slug}",
        )
        worker.start()
        return True, f"已启动后台刷新：{profile_label}。"

    def summarize_pipeline_state(pipeline_state: dict[str, object]) -> tuple[str, str, str]:
        steps = pipeline_state.get("steps", []) if isinstance(pipeline_state, dict) else []

        if pipeline_state.get("stopped"):
            for step in steps:
                if step.get("status") == "stopped":
                    return ("stopped", str(step.get("message") or "已手动停止。"), "")
            return (
                "stopped",
                str(pipeline_state.get("manual_stop_message") or "已手动停止。"),
                "",
            )

        for step in steps:
            if step.get("status") == "failed":
                return (
                    "failed",
                    str(step.get("message") or step.get("label") or "步骤失败"),
                    str(step.get("error_text") or step.get("message") or "步骤失败"),
                )

        for step in steps:
            if step.get("status") == "running":
                label = str(step.get("label") or step.get("key") or "当前步骤")
                return ("running", str(step.get("message") or f"正在执行 {label}"), "")

        for step in steps:
            if step.get("status") != "succeeded":
                label = str(step.get("label") or step.get("key") or "下一步")
                message = str(step.get("message") or f"等待 {label}")
                return ("pending", message, "")

        if steps:
            final_message = str(steps[-1].get("message") or "所有步骤已完成。")
            return ("succeeded", final_message, "")
        return ("pending", "尚未开始。", "")

    def parse_pipeline_timestamp(raw_value: object) -> datetime | None:
        if isinstance(raw_value, datetime):
            return raw_value
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def sync_tailor_run_from_workspace(
        run_id: int,
        workspace,
        *,
        session_id: str = "",
        last_message_override: str = "",
        error_override: str = "",
    ) -> None:
        tailor_service = web_app.config["tailor_service"]
        pipeline_state = tailor_service.load_pipeline_state(workspace)
        run_status, pipeline_message, pipeline_error = summarize_pipeline_state(pipeline_state)
        effective_session_id = session_id or str(pipeline_state.get("session_id") or "")
        last_message = error_override or last_message_override or pipeline_message
        error_text = error_override or pipeline_error
        finished_at = datetime.now(timezone.utc) if run_status in TERMINAL_RUN_STATUSES or run_status == "pending" else None
        repository.update_tailor_run(
            run_id,
            status=run_status,
            session_id=effective_session_id,
            current_step_key=str(pipeline_state.get("current_step") or ""),
            current_pid=None,
            result_json=json.dumps(pipeline_state, ensure_ascii=False),
            last_message=last_message,
            error_text=error_text,
            finished_at=finished_at,
        )
        for step in pipeline_state.get("steps", []):
            step_key = str(step.get("key") or "")
            if not step_key:
                continue
            repository.upsert_tailor_run_step(
                run_id,
                step_key,
                session_id=effective_session_id,
                status=str(step.get("status") or "pending"),
                prompt_path=str(step.get("prompt_path") or workspace.step_prompt_files[step_key]),
                last_message_path=str(
                    step.get("last_message_path") or workspace.step_message_files[step_key]
                ),
                log_path=str(step.get("log_path") or workspace.step_logs[step_key]),
                error_text=str(step.get("error_text") or ""),
                started_at=parse_pipeline_timestamp(step.get("started_at")),
                finished_at=parse_pipeline_timestamp(step.get("finished_at")),
            )

    def build_workspace_runtime(job) -> dict[str, object]:
        tailor_service = web_app.config["tailor_service"]
        workspace = tailor_service.ensure_workspace(job)
        pipeline_state = tailor_service.load_pipeline_state(workspace)
        pipeline_steps = pipeline_state.get("steps", []) if isinstance(pipeline_state, dict) else []
        revision_source_path, _, uses_final_resume = tailor_service.revision_resume_source(workspace)
        revision_advice_summary_text, derived_session_instruction_text = split_revision_advice(
            workspace.revision_advice_text
        )
        session_instruction_text = workspace.session_instruction_text.strip()
        if not session_instruction_text and not workspace.session_instruction_path.exists():
            session_instruction_text = derived_session_instruction_text
        session_instruction_updated_at = None
        if workspace.session_instruction_path.exists() and session_instruction_text:
            session_instruction_updated_at = datetime.fromtimestamp(
                workspace.session_instruction_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
        current_step_key = tailor_service.current_step_key(workspace)
        next_step_key = tailor_service.next_step_key(workspace)
        if next_step_key is None:
            current_step_label = "已完成"
        else:
            current_step_label = TAILOR_STEP_LABELS.get(current_step_key or next_step_key, "等待运行")
        next_step_label = TAILOR_STEP_LABELS.get(next_step_key or "", "") if next_step_key else ""
        completed_steps = sum(1 for step in pipeline_steps if step.get("status") == "succeeded")
        artifact_urls: dict[str, str] = {}
        for artifact_key in (
            "advice",
            "revision_advice",
            "matching_analysis",
            "tailored_resume",
            "fact_check_report",
            "session_instruction",
            "final_resume",
            "final_pdf",
            "diff_tex",
            "diff_pdf",
            "vibe_review",
        ):
            artifact_path = tailor_service.artifact_path(workspace, artifact_key)
            if artifact_path is not None and artifact_path.exists():
                cache_token = int(artifact_path.stat().st_mtime_ns)
                artifact_urls[artifact_key] = url_for(
                    "tailor_artifact",
                    job_id=job.id,
                    artifact_key=artifact_key,
                ) + f"?v={cache_token}"
        return {
            "workspace": workspace,
            "pipeline_state": pipeline_state,
            "pipeline_steps": pipeline_steps,
            "current_step_key": current_step_key,
            "next_step_key": next_step_key,
            "next_step_label": next_step_label,
            "current_step_label": current_step_label,
            "completed_steps": completed_steps,
            "current_step_log_text": tailor_service.current_step_log_text(workspace),
            "advice_text": workspace.advice_text,
            "advice_html": render_markdown_html(workspace.advice_text),
            "revision_advice_text": workspace.revision_advice_text,
            "revision_advice_html": render_markdown_html(workspace.revision_advice_text),
            "revision_advice_summary_text": revision_advice_summary_text,
            "revision_advice_summary_html": render_markdown_html(revision_advice_summary_text),
            "revision_advice_source_label": (
                "基于当前 final tex"
                if uses_final_resume
                else "当前无 final tex，已回退模板副本"
            ),
            "revision_advice_source_path": str(revision_source_path),
            "session_instruction_text": session_instruction_text,
            "session_instruction_html": render_markdown_html(session_instruction_text),
            "session_instruction_updated_at": session_instruction_updated_at,
            "matching_analysis_text": workspace.matching_analysis_text,
            "tailored_resume_text": workspace.tailored_resume_text,
            "fact_check_text": workspace.fact_check_text,
            "final_resume_text": workspace.final_resume_text,
            "diff_text": workspace.diff_text,
            "vibe_review_text": workspace.vibe_review_text,
            "artifact_urls": artifact_urls,
            "final_pdf_ready": workspace.final_resume_pdf_path.exists(),
            "diff_pdf_ready": workspace.diff_pdf_path.exists(),
            "advice_ready": workspace.advice_path.exists(),
            "advice_status": str(pipeline_state.get("advice_status") or "idle"),
            "advice_message": str(pipeline_state.get("advice_message") or ""),
            "advice_error": str(pipeline_state.get("advice_error") or ""),
            "advice_updated_at": pipeline_state.get("advice_updated_at"),
            "revision_advice_status": str(
                pipeline_state.get("revision_advice_status") or "idle"
            ),
            "revision_advice_message": str(
                pipeline_state.get("revision_advice_message") or ""
            ),
            "revision_advice_error": str(
                pipeline_state.get("revision_advice_error") or ""
            ),
            "revision_advice_updated_at": pipeline_state.get("revision_advice_updated_at"),
            "session_id": str(pipeline_state.get("session_id") or ""),
            "session_status": str(pipeline_state.get("session_status") or "not_started"),
            "session_established_at": pipeline_state.get("session_established_at"),
            "session_error": str(pipeline_state.get("session_error") or ""),
            "session_auto_ready": bool(session_instruction_text)
            and str(pipeline_state.get("session_status") or "not_started") == "ready",
        }

    def resolve_effective_session_state(
        *,
        runtime: dict[str, object],
        latest_run: TailorRun | None,
    ) -> tuple[str, str]:
        session_id = (
            latest_run.session_id
            if latest_run is not None and latest_run.session_id
            else str(runtime["session_id"] or "")
        )
        session_status = str(runtime["session_status"] or "not_started")
        if session_id and session_status == "not_started":
            session_status = "ready"
        return session_id, session_status

    def build_job_session_payload(job, *, message: str = "") -> dict[str, object]:
        latest_run = repository.latest_tailor_run_for_job(job.id or 0)
        runtime = build_workspace_runtime(job)
        tailor_service = web_app.config["tailor_service"]
        workspace_summary, history_items = build_tailor_history_views_for_job(job)
        active_session_id, active_session_status = resolve_effective_session_state(
            runtime=runtime,
            latest_run=latest_run,
        )
        active_status = latest_run.status if latest_run is not None else "idle"
        current_step_key = (
            latest_run.current_step_key
            if latest_run is not None and latest_run.current_step_key
            else ""
        )
        skill_payloads: dict[str, dict[str, object]] = {}
        for skill_key, skill_path in tailor_service.skill_items():
            skill_payloads[skill_key] = {
                "key": skill_key,
                "label": tailor_service.skill_label(skill_key),
                "path": str(skill_path),
                "detail_url": url_for("tailor_skill_detail", job_id=job.id, skill_key=skill_key),
                "reveal_url": url_for("reveal_tailor_skill_in_finder", job_id=job.id, skill_key=skill_key),
                "exists": skill_path.exists(),
            }
        return {
            "message": message,
            "job": {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "profile_label": job.profile_label,
                "source_site": job.source_site,
                "location_text": job.location_text,
                "job_url": job.job_url,
                "score": job.score,
            },
            "run": {
                "id": latest_run.id if latest_run is not None else None,
                "status": active_status,
                "current_step_key": current_step_key,
                "current_step_label": get_step_label(current_step_key) if current_step_key else "尚未开始",
                "last_message": latest_run.last_message if latest_run is not None else "",
                "error_text": latest_run.error_text if latest_run is not None else "",
                "updated_at": latest_run.updated_at.isoformat() if latest_run and latest_run.updated_at else None,
                "created_at": latest_run.created_at.isoformat() if latest_run and latest_run.created_at else None,
            },
            "workspace": {
                "label": runtime["workspace"].workspace_label,
                "base_resume_path": runtime["workspace"].base_resume_path,
                "base_resume_name": Path(runtime["workspace"].base_resume_path).name,
                "role_markdown": runtime["workspace"].role_markdown,
                "user_notes": runtime["workspace"].user_notes,
                "session_instruction_text": runtime["session_instruction_text"],
                "open_finder_available": sys.platform == "darwin",
            },
            "advice": {
                "ready": runtime["advice_ready"],
                "status": runtime["advice_status"],
                "message": runtime["advice_message"],
                "error": runtime["advice_error"],
                "updated_at": runtime["advice_updated_at"],
                "text": runtime["advice_text"],
                "html": runtime["advice_html"],
                "url": runtime["artifact_urls"].get("advice"),
            },
            "revision_advice": {
                "ready": bool(runtime["revision_advice_text"].strip()),
                "status": runtime["revision_advice_status"],
                "message": runtime["revision_advice_message"],
                "error": runtime["revision_advice_error"],
                "updated_at": runtime["revision_advice_updated_at"],
                "source_label": runtime["revision_advice_source_label"],
                "source_path": runtime["revision_advice_source_path"],
                "text": runtime["revision_advice_text"],
                "html": runtime["revision_advice_summary_html"],
                "url": runtime["artifact_urls"].get("revision_advice"),
            },
            "session_instruction": {
                "ready": bool(runtime["session_instruction_text"].strip()),
                "text": runtime["session_instruction_text"],
                "html": runtime["session_instruction_html"],
                "updated_at": runtime["session_instruction_updated_at"],
                "url": runtime["artifact_urls"].get("session_instruction"),
            },
            "session": {
                "ready": active_session_status == "ready" and bool(active_session_id),
                "status": active_session_status,
                "id": active_session_id,
                "established_at": runtime["session_established_at"],
                "error": runtime["session_error"],
                "auto_ready": active_session_status == "ready"
                and bool(runtime["session_instruction_text"].strip()),
            },
            "artifacts": {
                "final_resume_text": runtime["final_resume_text"],
                "final_pdf_url": runtime["artifact_urls"].get("final_pdf"),
                "diff_pdf_url": runtime["artifact_urls"].get("diff_pdf"),
                "final_pdf_ready": runtime["final_pdf_ready"],
                "diff_pdf_ready": runtime["diff_pdf_ready"],
            },
            "log": {
                "session_prompt_log": runtime["workspace"].action_logs["session_prompt"].read_text(encoding="utf-8")
                if runtime["workspace"].action_logs["session_prompt"].exists()
                else "",
                "advice_log": runtime["workspace"].action_logs["advice"].read_text(encoding="utf-8")
                if runtime["workspace"].action_logs["advice"].exists()
                else "",
                "revision_advice_log": runtime["workspace"].action_logs["revision_advice"].read_text(encoding="utf-8")
                if runtime["workspace"].action_logs["revision_advice"].exists()
                else "",
            },
            "skills": skill_payloads,
            "workspace_summary": workspace_summary
            or {
                "workspace_label": runtime["workspace"].workspace_label,
                "run_count": 0,
                "latest_status": "idle",
                "latest_step_label": "尚未开始",
                "latest_updated_at": None,
                "latest_session_id": "",
                "latest_message": "",
                "base_resume_name": Path(runtime["workspace"].base_resume_path).name,
            },
            "history": history_items,
        }

    def sync_tailor_run_snapshot(
        run_id: int,
        workspace,
        *,
        status: str,
        current_step_key: str,
        last_message: str,
        error_text: str = "",
        session_id: str = "",
        current_pid: int | None = None,
    ) -> None:
        tailor_service = web_app.config["tailor_service"]
        pipeline_state = tailor_service.load_pipeline_state(workspace)
        effective_session_id = session_id or str(pipeline_state.get("session_id") or "")
        repository.update_tailor_run(
            run_id,
            status=status,
            session_id=effective_session_id,
            current_step_key=current_step_key,
            current_pid=current_pid,
            result_json=json.dumps(pipeline_state, ensure_ascii=False),
            last_message=last_message,
            error_text=error_text,
            finished_at=datetime.now(timezone.utc) if status in TERMINAL_RUN_STATUSES else None,
        )

    def run_tailor_task(run_id: int, job_id: int, mode: str, step_key: str | None) -> None:
        repository = web_app.config["repository"]
        tailor_service = web_app.config["tailor_service"]
        run = repository.get_tailor_run(run_id)
        started_at = (
            run.started_at
            if run is not None and run.started_at is not None
            else datetime.now(timezone.utc)
        )
        repository.update_tailor_run(
            run_id,
            status="running",
            started_at=started_at,
            finished_at=None,
            error_text="",
        )

        try:
            job = repository.get_job(job_id)
            if job is None:
                raise RuntimeError("职位不存在")

            workspace = tailor_service.ensure_workspace(job)

            def on_process_state(observed_step_key: str, pid: int | None, observed_session_id: str) -> None:
                update_fields: dict[str, object] = {
                    "status": "running",
                    "current_step_key": observed_step_key,
                    "current_pid": pid,
                }
                if observed_session_id:
                    update_fields["session_id"] = observed_session_id
                repository.update_tailor_run(run_id, **update_fields)

            latest_run = repository.get_tailor_run(run_id)
            payload = tailor_service.run_pipeline_step(
                job,
                workspace,
                mode=mode,
                step_key=step_key,
                session_id=latest_run.session_id if latest_run else "",
                pid_callback=on_process_state,
            )
            sync_tailor_run_from_workspace(
                run_id,
                workspace,
                session_id=str(payload.get("session_id") or ""),
                last_message_override=str(payload.get("message") or ""),
            )
        except Exception as exc:
            job = repository.get_job(job_id)
            current_run = repository.get_tailor_run(run_id)
            if current_run is not None and current_run.status == "stopped":
                if job is not None:
                    workspace = tailor_service.ensure_workspace(job)
                    sync_tailor_run_from_workspace(
                        run_id,
                        workspace,
                        session_id=current_run.session_id,
                        last_message_override=current_run.last_message or "已手动停止当前精修任务。",
                    )
                return

            if job is not None:
                workspace = tailor_service.ensure_workspace(job)
                sync_tailor_run_from_workspace(
                    run_id,
                    workspace,
                    session_id=current_run.session_id if current_run else "",
                    last_message_override=str(exc),
                    error_override=str(exc),
                )
            else:
                repository.update_tailor_run(
                    run_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                    error_text=str(exc),
                )

    def run_advice_task(run_id: int, job_id: int) -> None:
        repository = web_app.config["repository"]
        tailor_service = web_app.config["tailor_service"]
        repository.update_tailor_run(
            run_id,
            status="running",
            current_step_key="advice",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            error_text="",
            last_message="正在生成流程建议。",
        )
        try:
            job = repository.get_job(job_id)
            if job is None:
                raise RuntimeError("职位不存在")
            workspace = tailor_service.ensure_workspace(job)

            def on_process_state(
                observed_step_key: str,
                pid: int | None,
                observed_session_id: str,
            ) -> None:
                repository.update_tailor_run(
                    run_id,
                    status="running",
                    current_step_key=observed_step_key,
                    current_pid=pid,
                    session_id=observed_session_id or "",
                )

            message = tailor_service.run_advice(job, workspace, pid_callback=on_process_state)
            sync_tailor_run_snapshot(
                run_id,
                workspace,
                status="succeeded",
                current_step_key="advice",
                last_message=message,
            )
        except Exception as exc:
            job = repository.get_job(job_id)
            if job is not None:
                workspace = tailor_service.ensure_workspace(job)
                sync_tailor_run_snapshot(
                    run_id,
                    workspace,
                    status="failed",
                    current_step_key="advice",
                    last_message=str(exc),
                    error_text=str(exc),
                )
            else:
                repository.update_tailor_run(
                    run_id,
                    status="failed",
                    current_step_key="advice",
                    finished_at=datetime.now(timezone.utc),
                    error_text=str(exc),
                )

    def run_revision_advice_task(run_id: int, job_id: int) -> None:
        repository = web_app.config["repository"]
        tailor_service = web_app.config["tailor_service"]
        repository.update_tailor_run(
            run_id,
            status="running",
            current_step_key="revision_advice",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            error_text="",
            last_message="正在生成修改建议。",
        )
        try:
            run = repository.get_tailor_run(run_id)
            job = repository.get_job(job_id)
            if job is None:
                raise RuntimeError("职位不存在")
            workspace = tailor_service.ensure_workspace(job)
            pipeline_state = tailor_service.load_pipeline_state(workspace)
            active_session_id = str(
                pipeline_state.get("session_id")
                or (run.session_id if run is not None else "")
                or ""
            )
            active_session_status = str(pipeline_state.get("session_status") or "not_started")
            if active_session_id and active_session_status == "not_started":
                active_session_status = "ready"

            def on_process_state(
                observed_step_key: str,
                pid: int | None,
                observed_session_id: str,
            ) -> None:
                repository.update_tailor_run(
                    run_id,
                    status="running",
                    current_step_key=observed_step_key,
                    current_pid=pid,
                    session_id=observed_session_id or active_session_id,
                )

            prefix_message = ""
            if active_session_status != "ready" or not active_session_id:
                prefix_message, active_session_id = tailor_service.start_session(
                    job,
                    workspace,
                    session_id=active_session_id,
                    pid_callback=on_process_state,
                )

            message = tailor_service.run_revision_advice(
                job,
                workspace,
                session_id=active_session_id,
                pid_callback=on_process_state,
            )
            sync_tailor_run_snapshot(
                run_id,
                workspace,
                status="succeeded",
                current_step_key="revision_advice",
                last_message=f"{prefix_message} {message}".strip(),
                session_id=active_session_id,
            )
        except Exception as exc:
            job = repository.get_job(job_id)
            if job is not None:
                workspace = tailor_service.ensure_workspace(job)
                sync_tailor_run_snapshot(
                    run_id,
                    workspace,
                    status="failed",
                    current_step_key="revision_advice",
                    last_message=str(exc),
                    error_text=str(exc),
                )
            else:
                repository.update_tailor_run(
                    run_id,
                    status="failed",
                    current_step_key="revision_advice",
                    finished_at=datetime.now(timezone.utc),
                    error_text=str(exc),
                )

    def run_md_agent_task(job_id: int, target_key: str, mode: str) -> None:
        repository = web_app.config["repository"]
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            return
        workspace = tailor_service.ensure_workspace(job)
        try:
            tailor_service.run_md_agent(
                job,
                workspace,
                target_key=target_key,
                mode=mode,
            )
        except Exception:
            # 中文注释：详细错误已由 pipeline_state 记录，这里不再重复吞吐到其他存储。
            pass

    def run_session_start_task(run_id: int, job_id: int) -> None:
        repository = web_app.config["repository"]
        tailor_service = web_app.config["tailor_service"]
        repository.update_tailor_run(
            run_id,
            status="running",
            current_step_key="session_start",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            error_text="",
            last_message="正在建立 Codex session。",
        )
        try:
            run = repository.get_tailor_run(run_id)
            job = repository.get_job(job_id)
            if run is None or job is None:
                raise RuntimeError("精修任务或职位不存在")
            workspace = tailor_service.ensure_workspace(job)

            def on_process_state(
                observed_step_key: str,
                pid: int | None,
                observed_session_id: str,
            ) -> None:
                repository.update_tailor_run(
                    run_id,
                    status="running",
                    current_step_key=observed_step_key,
                    current_pid=pid,
                    session_id=observed_session_id or run.session_id,
                )

            message, session_id = tailor_service.start_session(
                job,
                workspace,
                session_id=run.session_id,
                pid_callback=on_process_state,
            )
            sync_tailor_run_snapshot(
                run_id,
                workspace,
                status="succeeded",
                current_step_key="session_start",
                last_message=message,
                session_id=session_id,
            )
        except Exception as exc:
            run = repository.get_tailor_run(run_id)
            job = repository.get_job(job_id)
            if job is not None:
                workspace = tailor_service.ensure_workspace(job)
                sync_tailor_run_snapshot(
                    run_id,
                    workspace,
                    status="failed",
                    current_step_key="session_start",
                    last_message=str(exc),
                    error_text=str(exc),
                    session_id=run.session_id if run else "",
                )
            else:
                repository.update_tailor_run(
                    run_id,
                    status="failed",
                    current_step_key="session_start",
                    finished_at=datetime.now(timezone.utc),
                    error_text=str(exc),
                )

    def run_final_prompt_task(run_id: int, job_id: int, instruction_text: str) -> None:
        repository = web_app.config["repository"]
        tailor_service = web_app.config["tailor_service"]
        started_at = datetime.now(timezone.utc)
        repository.update_tailor_run(
            run_id,
            status="running",
            current_step_key="session_prompt",
            started_at=started_at,
            finished_at=None,
            error_text="",
        )

        try:
            run = repository.get_tailor_run(run_id)
            job = repository.get_job(job_id)
            if run is None or job is None:
                raise RuntimeError("精修任务或职位不存在")

            workspace = tailor_service.ensure_workspace(job)

            def on_process_state(
                observed_step_key: str,
                pid: int | None,
                observed_session_id: str,
            ) -> None:
                update_fields: dict[str, object] = {
                    "status": "running",
                    "current_step_key": observed_step_key,
                    "current_pid": pid,
                }
                if observed_session_id:
                    update_fields["session_id"] = observed_session_id
                repository.update_tailor_run(run_id, **update_fields)

            message, session_id = tailor_service.run_final_resume_prompt(
                job,
                workspace,
                instruction_text=instruction_text,
                session_id=run.session_id,
                pid_callback=on_process_state,
            )
            sync_tailor_run_snapshot(
                run_id,
                workspace,
                status="succeeded",
                current_step_key="session_prompt",
                last_message=message,
                session_id=session_id,
            )
        except Exception as exc:
            run = repository.get_tailor_run(run_id)
            job = repository.get_job(job_id)
            if job is not None:
                workspace = tailor_service.ensure_workspace(job)
                sync_tailor_run_snapshot(
                    run_id,
                    workspace,
                    status="failed",
                    current_step_key="session_prompt",
                    last_message=str(exc),
                    error_text=str(exc),
                    session_id=run.session_id if run else "",
                )
            else:
                repository.update_tailor_run(
                    run_id,
                    status="failed",
                    current_step_key="session_prompt",
                    finished_at=datetime.now(timezone.utc),
                    error_text=str(exc),
                )

    scheduler = build_scheduler(
        lambda: launch_refresh("all", trigger="scheduler"),
        settings.app.refresh_interval_minutes,
    )
    web_app.config["scheduler"] = scheduler

    @web_app.get("/")
    def root():
        return redirect(url_for("dashboard"))

    @web_app.get("/dashboard")
    def dashboard():
        service = web_app.config["service"]
        message = request.args.get("message", "")
        overview = repository.overview_counts()
        featured_jobs = build_jobs_view(min_score=62, limit=6, sort_by="score")
        recent_refresh_runs = repository.latest_refresh_runs(limit=6)
        recent_tailor_runs = build_tailor_workspace_views(limit=6)
        application_tracks = build_application_track_views(limit=6)
        track_stats = repository.application_track_stats()
        tailor_stats = repository.tailor_run_stats()
        source_site_overview = repository.source_site_overview()
        profiles_view = build_profiles_view()

        return render_template(
            "dashboard.html",
            **build_shell_context(
                current_page="dashboard",
                page_title="仪表盘",
                page_subtitle="整体看职位、抓取和精修任务的运行情况，不在这里放重操作。",
                page_sections=[
                    {"id": "dashboard-overview", "label": "整体统计"},
                    {"id": "dashboard-jobs", "label": "最近高分职位"},
                    {"id": "dashboard-refresh", "label": "最近抓取"},
                    {"id": "dashboard-tailor", "label": "最近精修"},
                    {"id": "dashboard-track", "label": "投递追踪"},
                ],
                page_eyebrow="Career Ops",
                page_badges=[
                    f"{len(service.enabled_profiles())} 个画像",
                    LOCAL_TIMEZONE_LABEL,
                ],
                message=message,
            ),
            overview=overview,
            profiles_view=profiles_view,
            source_site_overview=source_site_overview,
            featured_jobs=featured_jobs,
            refresh_runs=recent_refresh_runs,
            recent_tailor_runs=recent_tailor_runs,
            application_tracks=application_tracks,
            track_stats=track_stats,
            tailor_stats=tailor_stats,
        )

    @web_app.get("/crawler")
    def crawler():
        service = web_app.config["service"]
        scheduler = web_app.config["scheduler"]
        message = request.args.get("message", "")
        next_run = None
        scheduled_job = scheduler.get_job("refresh-all-profiles")
        if scheduled_job is not None:
            next_run = getattr(scheduled_job, "next_run_time", None)

        return render_template(
            "crawler.html",
            **build_shell_context(
                current_page="crawler",
                page_title="爬虫中心",
                page_subtitle="管理抓取状态、搜索画像、关键词和最近刷新记录。",
                page_sections=[
                    {"id": "crawler-status", "label": "运行状态"},
                    {"id": "crawler-profiles", "label": "搜索画像"},
                    {"id": "crawler-history", "label": "抓取记录"},
                ],
                page_eyebrow="Crawler Control",
                page_badges=[
                    f"自动刷新 {web_app.config['settings'].app.refresh_interval_minutes} 分钟",
                    LOCAL_TIMEZONE_LABEL,
                ],
                message=message,
            ),
            overview=repository.overview_counts(),
            profiles=service.enabled_profiles(),
            profiles_view=build_profiles_view(),
            refresh_runs=[build_refresh_run_view(run) for run in repository.latest_refresh_runs(limit=10)],
            next_run=next_run,
            source_site_overview=repository.source_site_overview(),
            scoring_model=build_scoring_model(),
            resume_profile=web_app.config["resume_profile"],
            site_options=["linkedin", "indeed", "zip_recruiter"],
            default_profile_resume=(
                service.enabled_profiles()[0].default_resume_file
                if service.enabled_profiles()
                else ""
            ),
        )

    @web_app.get("/crawler/runs/<int:run_id>")
    def crawler_run_detail(run_id: int):
        run = repository.get_refresh_run(run_id)
        if run is None:
            abort(404)

        run_view = build_refresh_run_view(run)
        return render_template(
            "crawler_run_detail.html",
            **build_shell_context(
                current_page="crawler",
                page_title=f"{run.profile_label} 抓取详情",
                page_subtitle="单次抓取的 query 粒度结果、错误和时间线都收在这里，主列表保持简洁。",
                page_sections=[
                    {"id": "crawler-run-summary", "label": "运行概览"},
                    {"id": "crawler-run-queries", "label": "Query 结果"},
                    {"id": "crawler-run-warnings", "label": "异常信息"},
                ],
                page_eyebrow="Crawler Run",
                page_badges=[
                    run.profile_label,
                    LOCAL_TIMEZONE_LABEL,
                ],
            ),
            run_view=run_view,
        )

    @web_app.get("/jobs")
    def jobs_page():
        settings = web_app.config["settings"]
        service = web_app.config["service"]
        profile_slug = request.args.get("profile_slug", "")
        min_score = request.args.get("min_score", default=settings.app.default_min_score, type=int)
        limit = request.args.get("limit", default=settings.app.default_limit, type=int)
        location_query = request.args.get("location_query", "").strip()
        include_keywords_raw = request.args.get("include_keywords", "").strip()
        exclude_keywords_raw = request.args.get("exclude_keywords", "").strip()
        recent_hours = request.args.get("recent_hours", default=0, type=int)
        sort_by = request.args.get("sort_by", "recent").strip()
        if sort_by not in {"recent", "score"}:
            sort_by = "recent"
        include_keywords = split_multiline_input(include_keywords_raw)
        exclude_keywords = split_multiline_input(exclude_keywords_raw)
        selected_countries = normalize_selected_countries(request.args.getlist("countries"))
        country_stats = repository.country_stats(profile_slug=profile_slug or None)
        jobs_counts = repository.jobs_filter_counts(
            profile_slug=profile_slug or None,
            min_score=float(min_score),
            countries=selected_countries,
            location_query=location_query,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            recent_hours=recent_hours,
            sort_by=sort_by,
        )
        jobs_view = build_jobs_view(
            profile_slug=profile_slug or None,
            min_score=float(min_score),
            limit=limit,
            countries=selected_countries,
            location_query=location_query,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            recent_hours=recent_hours,
            sort_by=sort_by,
        )
        excluded_companies = repository.list_excluded_companies()

        page_message = request.args.get("message", "")
        current_query_url = request.full_path[:-1] if request.full_path.endswith("?") else request.full_path
        jobs_sort_urls = {
            "recent": url_for(
                "jobs_page",
                profile_slug=profile_slug,
                min_score=min_score,
                limit=limit,
                location_query=location_query,
                include_keywords=include_keywords_raw,
                exclude_keywords=exclude_keywords_raw,
                recent_hours=recent_hours,
                sort_by="recent",
                countries=selected_countries,
            ),
            "score": url_for(
                "jobs_page",
                profile_slug=profile_slug,
                min_score=min_score,
                limit=limit,
                location_query=location_query,
                include_keywords=include_keywords_raw,
                exclude_keywords=exclude_keywords_raw,
                recent_hours=recent_hours,
                sort_by="score",
                countries=selected_countries,
            ),
        }

        return render_template(
            "jobs.html",
            **build_shell_context(
                current_page="jobs",
                page_title="Jobs",
                page_subtitle="完整筛选职位列表，并从这里进入单个岗位的简历精修。",
                page_sections=[
                    {"id": "jobs-filters", "label": "筛选工具栏"},
                    {"id": "jobs-table", "label": "职位表格"},
                ],
                page_eyebrow="Pipeline",
                page_badges=[
                    f"剩余 {jobs_counts['remaining_count']}",
                    f"已投递 {jobs_counts['applied_count']}",
                    f"已查阅 {jobs_counts['reviewed_count']}",
                    f"最低分 {min_score}",
                ],
                message=page_message,
            ),
            jobs_view=jobs_view,
            jobs_counts=jobs_counts,
            profiles=service.enabled_profiles(),
            active_profile_slug=profile_slug,
            min_score=min_score,
            limit=limit,
            recent_hours=recent_hours,
            sort_by=sort_by,
            selected_countries=selected_countries,
            selected_country_set=set(selected_countries),
            country_stats=country_stats,
            country_stats_map={item["country"]: item["job_count"] for item in country_stats},
            country_options=COUNTRY_FILTER_OPTIONS,
            location_query=location_query,
            include_keywords=include_keywords_raw,
            exclude_keywords=exclude_keywords_raw,
            current_query_url=current_query_url,
            jobs_sort_urls=jobs_sort_urls,
            excluded_companies=excluded_companies,
        )

    @web_app.post("/jobs/excluded-companies")
    def create_excluded_company_entry():
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("jobs_page")
        )
        separator = "&" if "?" in redirect_target else "?"
        company_name = " ".join(request.form.get("company_name", "").split())
        if not company_name:
            return redirect(f"{redirect_target}{separator}message=公司名不能为空。")
        repository.create_excluded_company(company_name)
        return redirect(f"{redirect_target}{separator}message=已加入排除公司：{company_name}。")

    @web_app.post("/jobs/excluded-companies/<int:company_id>/delete")
    def delete_excluded_company_entry(company_id: int):
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("jobs_page")
        )
        separator = "&" if "?" in redirect_target else "?"
        if not repository.delete_excluded_company(company_id):
            abort(404)
        return redirect(f"{redirect_target}{separator}message=已移除排除公司。")

    @web_app.post("/jobs/<int:job_id>/exclude-company")
    def exclude_job_company(job_id: int):
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("jobs_page")
        )
        separator = "&" if "?" in redirect_target else "?"
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        repository.create_excluded_company(job.company)
        message = f"已排除公司 {job.company}，相关职位后续不会再出现在列表中。"
        if is_async_request():
            return json_message(message, payload={"job_id": job_id, "remove_job": True})
        return redirect(f"{redirect_target}{separator}message={message}")

    @web_app.post("/jobs/<int:job_id>/application")
    def update_job_application(job_id: int):
        action = request.form.get("action", "mark")
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("jobs_page")
        )
        separator = "&" if "?" in redirect_target else "?"

        if action == "clear":
            repository.sync_application_track_for_job(job_id, applied_at=None)
            message = "已取消投递标记。"
            if is_async_request():
                return json_message(message, payload={"job_id": job_id, "remove_job": False})
            return redirect(f"{redirect_target}{separator}message={message}")

        # 中文注释：职位页里的投递标记和独立 Tracker 必须同步，避免两个入口状态不一致。
        repository.sync_application_track_for_job(job_id, applied_at=datetime.now(timezone.utc))
        message = "已标记为已投递。"
        if is_async_request():
            return json_message(message, payload={"job_id": job_id, "remove_job": True})
        return redirect(f"{redirect_target}{separator}message={message}")

    @web_app.post("/jobs/<int:job_id>/dismiss")
    def dismiss_job(job_id: int):
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("jobs_page")
        )
        separator = "&" if "?" in redirect_target else "?"

        job = repository.dismiss_job(job_id, dismissed_at=datetime.now(timezone.utc))
        if job is None:
            abort(404)
        message = "已标记为不合适，后续不会再出现在职位表格里。"
        if is_async_request():
            return json_message(message, payload={"job_id": job_id, "remove_job": True})
        return redirect(f"{redirect_target}{separator}message={message}")

    @web_app.get("/application-tracker")
    def application_tracker():
        source_kind = request.args.get("source_kind", "").strip()
        if source_kind not in {"linked", "manual"}:
            source_kind = ""
        keyword = " ".join(request.args.get("keyword", "").split())
        stage = request.args.get("stage", "").strip()
        if stage not in TRACK_STAGE_OPTIONS:
            stage = ""
        chart_range = request.args.get("chart_range", "all").strip().lower()
        if chart_range not in TRACKER_CHART_RANGE_LABELS:
            chart_range = "all"
        limit = request.args.get("limit", default=50, type=int)
        current_query_params: dict[str, object] = {}
        if source_kind:
            current_query_params["source_kind"] = source_kind
        if keyword:
            current_query_params["keyword"] = keyword
        if stage:
            current_query_params["stage"] = stage
        if limit != 50:
            current_query_params["limit"] = limit
        if chart_range != "all":
            current_query_params["chart_range"] = chart_range
        current_query_url = url_for("application_tracker", **current_query_params)
        clear_filters_params: dict[str, object] = {}
        if chart_range != "all":
            clear_filters_params["chart_range"] = chart_range
        clear_filters_url = url_for("application_tracker", **clear_filters_params)
        active_filter_tokens: list[str] = []
        if source_kind == "linked":
            active_filter_tokens.append("关联职位")
        elif source_kind == "manual":
            active_filter_tokens.append("手工录入")
        if stage:
            active_filter_tokens.append(TRACK_STAGE_LABELS.get(stage, stage))
        if keyword:
            active_filter_tokens.append(f"关键词：{keyword}")
        active_filter_label = " / ".join(active_filter_tokens) if active_filter_tokens else "全部"
        application_tracks = build_application_track_views(
            source_kind=source_kind or None,
            keyword=keyword or None,
            stage=stage or None,
            limit=limit,
        )
        tracker_chart = build_application_track_chart_view(range_key=chart_range)
        chart_range_urls = {
            range_key: url_for(
                "application_tracker",
                **(
                    {
                        **{
                            key: value
                            for key, value in current_query_params.items()
                            if key != "chart_range"
                        },
                        **({"chart_range": range_key} if range_key != "all" else {}),
                    }
                ),
            )
            for range_key in TRACKER_CHART_RANGE_LABELS
        }
        track_stats = repository.application_track_stats()
        return render_template(
            "application_tracker.html",
            **build_shell_context(
                current_page="application_tracker",
                page_title="投递追踪",
                page_subtitle="把已投递岗位和手工补录记录集中放在一个运营页面里。",
                page_sections=[
                    {"id": "tracker-summary", "label": "追踪概览"},
                    {"id": "tracker-manual", "label": "手工新增"},
                    {"id": "tracker-list", "label": "追踪列表"},
                ],
                page_eyebrow="Application Tracker",
                page_badges=[f"总追踪 {track_stats['total']}", LOCAL_TIMEZONE_LABEL],
                message=request.args.get("message", ""),
                page_actions=[
                    {"label": "回到 Jobs", "href": url_for("jobs_page"), "kind": "ghost"},
                ],
            ),
            application_tracks=application_tracks,
            track_stats=track_stats,
            active_source_kind=source_kind,
            active_keyword=keyword,
            active_stage=stage,
            active_filter_label=active_filter_label,
            limit=limit,
            current_query_url=current_query_url,
            clear_filters_url=clear_filters_url,
            chart_range=chart_range,
            chart_range_labels=TRACKER_CHART_RANGE_LABELS,
            chart_range_urls=chart_range_urls,
            tracker_chart=tracker_chart,
            stage_options=TRACK_STAGE_OPTIONS,
            stage_labels=TRACK_STAGE_LABELS,
            default_applied_at_local=format_local_time(
                datetime.now(timezone.utc),
                "%Y-%m-%dT%H:%M",
            ),
            default_stage_event_local=format_local_time(
                datetime.now(timezone.utc),
                "%Y-%m-%dT%H:%M",
            ),
        )

    @web_app.post("/application-tracker/manual")
    def create_manual_application_track_entry():
        title = " ".join(request.form.get("title", "").split())
        company = " ".join(request.form.get("company", "").split())
        source_site = " ".join(request.form.get("source_site", "").split()).lower()
        profile_label = " ".join(request.form.get("profile_label", "").split())
        job_url = request.form.get("job_url", "").strip()
        notes = request.form.get("notes", "").strip()
        applied_at_raw = request.form.get("applied_at_local", "").strip()
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("application_tracker")
        )
        separator = "&" if "?" in redirect_target else "?"

        if not title or not company:
            return redirect(f"{redirect_target}{separator}message=职位名称和公司不能为空。")

        try:
            applied_at = (
                parse_local_datetime_input(applied_at_raw)
                if applied_at_raw
                else datetime.now(timezone.utc)
            )
        except ValueError:
            return redirect(f"{redirect_target}{separator}message=投递时间格式不正确。")

        repository.create_manual_application_track(
            ApplicationTrack(
                source_kind="manual",
                title=title,
                company=company,
                source_site=source_site or "manual",
                profile_label=profile_label,
                job_url=job_url,
                notes=notes,
                applied_at=applied_at,
            )
        )
        return redirect(f"{redirect_target}{separator}message=已新增手工投递追踪。")

    @web_app.post("/application-tracker/<int:track_id>/events")
    def add_application_track_event_entry(track_id: int):
        stage = request.form.get("stage", "submitted").strip()
        notes = request.form.get("notes", "").strip()
        occurred_at_raw = request.form.get("occurred_at_local", "").strip()
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("application_tracker")
        )
        separator = "&" if "?" in redirect_target else "?"

        if stage not in TRACK_STAGE_OPTIONS:
            return redirect(f"{redirect_target}{separator}message=阶段不合法。")

        try:
            occurred_at = (
                parse_local_datetime_input(occurred_at_raw)
                if occurred_at_raw
                else datetime.now(timezone.utc)
            )
        except ValueError:
            return redirect(f"{redirect_target}{separator}message=阶段时间格式不正确。")

        event = repository.add_application_track_event(
            track_id,
            stage=stage,
            occurred_at=occurred_at,
            notes=notes,
        )
        if event is None:
            abort(404)
        return redirect(
            f"{redirect_target}{separator}message=已更新到 {TRACK_STAGE_LABELS[stage]}。"
        )

    @web_app.post("/application-tracker/<int:track_id>/delete")
    def delete_application_track_entry(track_id: int):
        return_to = request.form.get("return_to", "")
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else url_for("application_tracker")
        )
        separator = "&" if "?" in redirect_target else "?"

        track = repository.get_application_track(track_id)
        if track is None:
            abort(404)

        if track.source_kind == "linked" and track.job_id is not None:
            repository.sync_application_track_for_job(track.job_id, applied_at=None)
            return redirect(f"{redirect_target}{separator}message=已取消关联职位的投递追踪。")

        repository.delete_application_track(track_id)
        return redirect(f"{redirect_target}{separator}message=已删除手工投递追踪。")

    @web_app.get("/tailor-tasks")
    def tailor_tasks():
        service = web_app.config["service"]
        status = request.args.get("status", "").strip()
        profile_slug = request.args.get("profile_slug", "").strip()
        limit = request.args.get("limit", default=40, type=int)
        tailor_stats = repository.tailor_run_stats()
        tailor_runs = build_tailor_workspace_views(
            status=status or None,
            profile_slug=profile_slug or None,
            limit=limit,
        )
        return render_template(
            "tailor_tasks.html",
            **build_shell_context(
                current_page="tailor_tasks",
                page_title="Tailor Sessions",
                page_subtitle="按职位工作区管理建议、session 和最新 PDF，避免同一 job 的重复 run 挤满列表。",
                page_sections=[
                    {"id": "tailor-summary", "label": "会话概览"},
                    {"id": "tailor-table", "label": "会话列表"},
                ],
                page_eyebrow="Tailor Sessions",
                page_badges=[
                    f"总任务 {tailor_stats['total']}",
                    f"运行中 {tailor_stats['running']}",
                ],
                message=request.args.get("message", ""),
            ),
            tailor_stats=tailor_stats,
            tailor_runs=tailor_runs,
            statuses=["pending", "running", "succeeded", "failed", "stopped"],
            active_status=status,
            active_profile_slug=profile_slug,
            profiles=service.enabled_profiles(),
            limit=limit,
        )

    @web_app.post("/tailor-runs/<int:run_id>/stop")
    def stop_tailor_run(run_id: int):
        tailor_service = web_app.config["tailor_service"]
        run = repository.get_tailor_run(run_id)
        if run is None:
            abort(404)

        return_to = request.form.get("return_to", "").strip()
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else (
                url_for("job_detail", job_id=run.job_id)
                if run.job_id
                else url_for("tailor_tasks")
            )
        )
        separator = "&" if "?" in redirect_target else "?"

        if run.status not in ACTIVE_RUN_STATUSES:
            message = "当前精修任务不在运行。"
            if is_async_request():
                job = repository.get_job(run.job_id)
                payload = build_job_session_payload(job, message=message) if job is not None else {}
                return json_message(message, payload=payload, status=409)
            return redirect(f"{redirect_target}{separator}message={message}")

        job = repository.get_job(run.job_id)
        if job is None:
            abort(404)
        workspace = tailor_service.ensure_workspace(job)
        tailor_service.mark_step_stopped(
            workspace,
            step_key=run.current_step_key or tailor_service.current_step_key(workspace),
            message="已手动停止当前精修任务。",
        )
        if run.current_pid:
            try:
                os.kill(run.current_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        sync_tailor_run_from_workspace(
            run_id,
            workspace,
            session_id=run.session_id,
            last_message_override="已手动停止当前精修任务。",
        )
        repository.update_tailor_run(
            run_id,
            status="stopped",
            current_step_key=run.current_step_key,
            current_pid=None,
            finished_at=datetime.now(timezone.utc),
        )
        message = "已停止精修任务。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(f"{redirect_target}{separator}message={message}")

    @web_app.post("/tailor-runs/<int:run_id>/delete")
    def delete_tailor_run(run_id: int):
        tailor_service = web_app.config["tailor_service"]
        run = repository.get_tailor_run(run_id)
        if run is None:
            abort(404)

        return_to = request.form.get("return_to", "").strip()
        redirect_target = (
            strip_message_query(return_to)
            if return_to.startswith("/") and not return_to.startswith("//")
            else (
                url_for("job_detail", job_id=run.job_id)
                if run.job_id
                else url_for("tailor_tasks")
            )
        )
        separator = "&" if "?" in redirect_target else "?"

        if run.status in ACTIVE_RUN_STATUSES:
            message = "请先停止当前精修任务。"
            if is_async_request():
                job = repository.get_job(run.job_id)
                payload = build_job_session_payload(job, message=message) if job is not None else {}
                return json_message(message, payload=payload, status=409)
            return redirect(f"{redirect_target}{separator}message={message}")

        related_runs = [
            item
            for item in repository.list_tailor_runs_for_job(run.job_id, limit=200)
            if item.workspace_dir == run.workspace_dir
        ]
        for item in related_runs:
            if item.id is not None:
                repository.delete_tailor_run(item.id)
        workspace_deleted = (
            tailor_service.delete_workspace(run.workspace_dir)
            if run.workspace_dir
            else False
        )
        deletion_message = (
            "已删除精修任务与 Tailor 工作区。"
            if workspace_deleted
            else "已删除精修任务记录。"
        )
        if is_async_request():
            return json_message(
                deletion_message,
                payload={"redirect_url": url_for("jobs_page"), "deleted": True},
            )
        return redirect(f"{redirect_target}{separator}message={deletion_message}")

    @web_app.post("/refresh")
    def refresh_jobs():
        profile_slug = request.form.get("profile_slug", "all")
        redirect_to = resolve_redirect_endpoint(request.form.get("redirect_to"), default="crawler")
        _, summary = launch_refresh(profile_slug, trigger="manual")
        return redirect(url_for(redirect_to, message=summary))

    @web_app.post("/profiles/<profile_slug>/terms")
    def add_profile_term(profile_slug: str):
        service = web_app.config["service"]
        redirect_to = resolve_redirect_endpoint(request.form.get("redirect_to"), default="crawler")
        search_term = " ".join(request.form.get("search_term", "").split())
        profile = next((item for item in service.enabled_profiles() if item.slug == profile_slug), None)
        if profile is None:
            abort(404)
        if not search_term:
            return redirect(url_for(redirect_to, message="关键词不能为空。"))

        save_search_terms(profile_slug, list(profile.search_terms) + [search_term])
        rebuild_runtime_state()
        return redirect(url_for(redirect_to, message=f"已为 {profile.label} 添加关键词。"))

    @web_app.post("/profiles")
    def create_profile():
        redirect_to = resolve_redirect_endpoint(request.form.get("redirect_to"), default="crawler")
        label = " ".join(request.form.get("label", "").split())
        slug = " ".join(request.form.get("slug", "").split())
        search_terms = split_multiline_input(request.form.get("search_terms", ""))
        locations = split_location_input(request.form.get("locations", ""))
        default_resume_file = " ".join(request.form.get("default_resume_file", "").split())
        sites = request.form.getlist("sites")

        try:
            profile_slug = add_search_profile(
                label=label,
                slug=slug,
                search_terms=search_terms,
                locations=locations,
                sites=sites,
                default_resume_file=default_resume_file,
            )
        except ValueError as exc:
            return redirect(url_for(redirect_to, message=f"新增画像失败：{exc}"))

        rebuild_runtime_state()
        return redirect(url_for(redirect_to, message=f"已新增搜索画像：{profile_slug}。"))

    @web_app.post("/profiles/<profile_slug>/terms/delete")
    def delete_profile_term(profile_slug: str):
        service = web_app.config["service"]
        redirect_to = resolve_redirect_endpoint(request.form.get("redirect_to"), default="crawler")
        search_term = request.form.get("search_term", "")
        profile = next((item for item in service.enabled_profiles() if item.slug == profile_slug), None)
        if profile is None:
            abort(404)

        updated_terms = [item for item in profile.search_terms if item != search_term]
        save_search_terms(profile_slug, updated_terms)
        rebuild_runtime_state()
        return redirect(url_for(redirect_to, message=f"已从 {profile.label} 删除关键词。"))

    @web_app.post("/profiles/<profile_slug>/locations")
    def update_profile_locations(profile_slug: str):
        service = web_app.config["service"]
        redirect_to = resolve_redirect_endpoint(request.form.get("redirect_to"), default="crawler")
        profile = next((item for item in service.enabled_profiles() if item.slug == profile_slug), None)
        if profile is None:
            abort(404)

        locations = split_location_input(request.form.get("locations", ""))
        save_profile_locations(profile_slug, locations)
        rebuild_runtime_state()
        return redirect(url_for(redirect_to, message=f"已更新 {profile.label} 的搜索地点。"))

    @web_app.post("/profiles/<profile_slug>/delete")
    def delete_profile(profile_slug: str):
        redirect_to = resolve_redirect_endpoint(request.form.get("redirect_to"), default="crawler")
        try:
            delete_search_profile(profile_slug)
        except KeyError:
            abort(404)
        rebuild_runtime_state()
        return redirect(url_for(redirect_to, message=f"已移除搜索画像：{profile_slug}。"))

    @web_app.get("/jobs/<int:job_id>")
    def job_detail(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        payload = build_job_session_payload(job, message=request.args.get("message", ""))
        runtime = build_workspace_runtime(job)
        latest_run = repository.latest_tailor_run_for_job(job_id)
        message = request.args.get("message", "")

        return render_template(
            "job_detail.html",
            **build_shell_context(
                current_page="jobs",
                page_title=job.title,
                page_subtitle=f"{job.company} · {job.location_text or '地点未注明'} · {job.source_site}",
                page_sections=[
                    {"id": "job-workspace", "label": "工作区"},
                    {"id": "job-preview", "label": "PDF 预览"},
                ],
                page_eyebrow="Tailor Session",
                page_badges=[f"匹配分 {job.score:.1f}", job_country_label(job)],
                page_actions=(
                    [
                        {
                            "label": "打开职位页",
                            "href": job.job_url,
                            "kind": "ghost",
                            "target_blank": True,
                        }
                    ]
                    if job.job_url
                    else []
                ),
                message=message,
            ),
            job=job,
            job_country=job_country_label(job),
            workspace=runtime["workspace"],
            latest_run=latest_run,
            workspace_summary=payload["workspace_summary"],
            history_runs=payload["history"],
            available_resume_files=tailor_service.available_resume_files(),
            page_payload=payload,
            revision_advice_text=runtime["revision_advice_text"],
            revision_advice_html=runtime["revision_advice_summary_html"],
            revision_advice_source_label=runtime["revision_advice_source_label"],
            session_instruction_text=runtime["session_instruction_text"],
            session_instruction_html=runtime["session_instruction_html"],
            session_instruction_updated_at=runtime["session_instruction_updated_at"],
            artifact_urls=runtime["artifact_urls"],
            final_pdf_ready=runtime["final_pdf_ready"],
            diff_pdf_ready=runtime["diff_pdf_ready"],
            session_id=payload["session"]["id"],
            session_status=payload["session"]["status"],
            session_established_at=runtime["session_established_at"],
            session_error=runtime["session_error"],
            revision_advice_status=runtime["revision_advice_status"],
            revision_advice_message=runtime["revision_advice_message"],
            revision_advice_updated_at=runtime["revision_advice_updated_at"],
            current_run_step_label=payload["run"]["current_step_label"],
            final_prompt_available=payload["session"]["ready"],
        )

    @web_app.get("/jobs/<int:job_id>/preview")
    def job_preview(job_id: int):
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        return render_template(
            "job_preview.html",
            **build_shell_context(
                current_page="jobs",
                page_title=job.title,
                page_subtitle=f"{job.company} · {job.location_text or '地点未注明'} · {job.source_site}",
                page_sections=[
                    {"id": "job-preview-summary", "label": "岗位概览"},
                    {"id": "job-preview-description", "label": "岗位描述"},
                    {"id": "job-preview-fit", "label": "匹配备注"},
                ],
                page_eyebrow="Job Preview",
                page_badges=[f"匹配分 {job.score:.1f}", job_country_label(job)],
                page_actions=(
                    [
                        {
                            "label": "打开原始职位页",
                            "href": job.job_url,
                            "kind": "primary",
                            "target_blank": True,
                        }
                    ]
                    if job.job_url
                    else []
                ),
                message=request.args.get("message", ""),
            ),
            job=job,
            job_country=job_country_label(job),
        )

    @web_app.get("/jobs/browser-window-marker")
    def job_browser_window_marker():
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="robots" content="noindex,nofollow" />
    <title>{JOB_BROWSER_WINDOW_MARKER_TITLE}</title>
  </head>
  <body>
    <p>{JOB_BROWSER_WINDOW_MARKER_TEXT}</p>
  </body>
</html>
"""

    @web_app.post("/jobs/<int:job_id>/open-browser-window")
    def open_job_browser_window(job_id: int):
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        target_url = (
            job.job_url
            or f"{request.host_url.rstrip('/')}{url_for('job_preview', job_id=job_id)}"
        )
        payload = {
            "opened_url": target_url,
            "mode": "chrome_dedicated_window",
            "site_behavior": chrome_site_behavior_for_url(target_url),
            "plugin_mode": "reuse_chrome_profile_state",
        }

        if sys.platform != "darwin":
            message = "当前系统不是 macOS，无法复用专用 Chrome 岗位工作窗。"
            if is_async_request():
                return json_message(message, payload={**payload, "fallback": True})
            return redirect(target_url)

        state_path = web_app.config["browser_window_state_path"]
        marker_url = f"{request.host_url.rstrip('/')}{url_for('job_browser_window_marker')}"
        try:
            open_result = open_url_in_dedicated_chrome_window(
                target_url,
                state_path=state_path,
                marker_url=marker_url,
                site_behavior=str(payload["site_behavior"]),
            )
        except subprocess.CalledProcessError as exc:
            detail = subprocess_failure_detail(exc)
            message = "Chrome 专用岗位工作窗打开失败。"
            if detail:
                message = f"{message} {detail}"
            if is_async_request():
                return json_message(message, payload={**payload, "fallback": True})
            return redirect(target_url)
        except Exception as exc:
            message = f"Chrome 专用岗位工作窗打开失败：{exc}"
            if is_async_request():
                return json_message(message, payload={**payload, "fallback": True})
            return redirect(target_url)

        warning = open_result.warning.strip()
        if payload["site_behavior"] == "linkedin_auto_expand":
            message = (
                "已在专用 Chrome 岗位工作窗中打开当前 LinkedIn 职位，并自动尝试展开折叠内容。"
                "当前复用你的 Chrome 配置，扩展状态按浏览器原有设置保持。"
            )
        else:
            message = (
                "已在专用 Chrome 岗位工作窗中打开当前职位。"
                "当前复用你的 Chrome 配置，扩展状态按浏览器原有设置保持。"
            )
        response_payload = {**payload, "fallback": False}
        if warning:
            message = f"{message} {warning}"
            response_payload["warning"] = warning
        if is_async_request():
            return json_message(message, payload=response_payload)
        return redirect(target_url)

    @web_app.post("/jobs/<int:job_id>/tailor/workspace")
    def save_tailor_workspace(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status == "running":
            message = "当前有任务在运行，先停止再保存工作区。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=409)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        workspace = tailor_service.save_workspace(
            job,
            base_resume_path=request.form.get("base_resume_path", ""),
            role_markdown=request.form.get("role_markdown", ""),
            user_notes=request.form.get("user_notes", ""),
            session_instruction_text=request.form.get("instruction_text", ""),
        )
        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status != "running":
            sync_tailor_run_from_workspace(latest_run.id or 0, workspace)
        message = "本地工作区已保存。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/advice")
    def run_tailor_advice(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status == "running":
            message = "已有精修任务在运行。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=409)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        workspace = tailor_service.save_workspace(
            job,
            base_resume_path=request.form.get("base_resume_path", ""),
            role_markdown=request.form.get("role_markdown", ""),
            user_notes=request.form.get("user_notes", ""),
            session_instruction_text=request.form.get("instruction_text", ""),
        )
        pipeline_state = tailor_service.load_pipeline_state(workspace)
        active_session_id, _ = resolve_effective_session_state(
            runtime=build_workspace_runtime(job),
            latest_run=latest_run,
        )
        run = repository.create_tailor_run(
            TailorRun(
                job_id=job.id or 0,
                profile_slug=job.profile_slug,
                workspace_dir=str(workspace.workspace_dir),
                base_resume_path=workspace.base_resume_path,
                session_id=active_session_id or str(pipeline_state.get("session_id") or ""),
                status="pending",
                current_step_key="revision_advice",
                request_payload=json.dumps(
                    {
                        "job_id": job.id,
                        "workspace_dir": str(workspace.workspace_dir),
                        "mode": "one_click_generate",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        worker = threading.Thread(
            target=run_revision_advice_task,
            args=(run.id or 0, job_id),
            daemon=True,
            name=f"tailor-generate-{job_id}-{run.id}",
        )
        worker.start()
        message = "已开始一键生成：会复用或建立当前 Session，并生成修改建议。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/revision-advice")
    def run_tailor_revision_advice(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status == "running":
            message = "已有精修任务在运行。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=409)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        workspace = tailor_service.save_workspace(
            job,
            base_resume_path=request.form.get("base_resume_path", ""),
            role_markdown=request.form.get("role_markdown", ""),
            user_notes=request.form.get("user_notes", ""),
            session_instruction_text=request.form.get("instruction_text", ""),
        )
        pipeline_state = tailor_service.load_pipeline_state(workspace)
        active_session_id, _ = resolve_effective_session_state(
            runtime=build_workspace_runtime(job),
            latest_run=latest_run,
        )
        run = repository.create_tailor_run(
            TailorRun(
                job_id=job.id or 0,
                profile_slug=job.profile_slug,
                workspace_dir=str(workspace.workspace_dir),
                base_resume_path=workspace.base_resume_path,
                session_id=active_session_id or str(pipeline_state.get("session_id") or ""),
                status="pending",
                current_step_key="revision_advice",
                request_payload=json.dumps(
                    {
                        "job_id": job.id,
                        "workspace_dir": str(workspace.workspace_dir),
                        "mode": "revision_advice",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        worker = threading.Thread(
            target=run_revision_advice_task,
            args=(run.id or 0, job_id),
            daemon=True,
            name=f"tailor-revision-advice-{job_id}-{run.id}",
        )
        worker.start()
        message = "已开始重新生成修改建议：会复用当前 Session，必要时自动恢复。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/session/start")
    def start_tailor_session(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status == "running":
            message = "已有精修任务在运行。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=409)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        workspace = tailor_service.save_workspace(
            job,
            base_resume_path=request.form.get("base_resume_path", ""),
            role_markdown=request.form.get("role_markdown", ""),
            user_notes=request.form.get("user_notes", ""),
            session_instruction_text=request.form.get("instruction_text", ""),
        )
        latest_run = repository.latest_tailor_run_for_job(job_id)
        runtime = build_workspace_runtime(job)
        existing_session_id, effective_session_status = resolve_effective_session_state(
            runtime=runtime,
            latest_run=latest_run,
        )
        if effective_session_status == "ready" and existing_session_id:
            message = "当前 Codex session 已可直接使用。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message))
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        run = repository.create_tailor_run(
            TailorRun(
                job_id=job.id or 0,
                profile_slug=job.profile_slug,
                workspace_dir=str(workspace.workspace_dir),
                base_resume_path=workspace.base_resume_path,
                session_id=existing_session_id,
                status="pending",
                current_step_key="session_start",
                request_payload=json.dumps(
                    {
                        "job_id": job.id,
                        "workspace_dir": str(workspace.workspace_dir),
                        "mode": "session_start",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        worker = threading.Thread(
            target=run_session_start_task,
            args=(run.id or 0, job_id),
            daemon=True,
            name=f"tailor-session-start-{job_id}-{run.id}",
        )
        worker.start()
        message = "已开始建立 Codex session。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/run")
    def run_tailor(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        mode = request.form.get("mode", "next").strip()
        if mode not in {"restart", "next", "step"}:
            mode = "next"
        step_key = request.form.get("step_key", "").strip() or None
        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status == "running":
            return redirect(url_for("job_detail", job_id=job_id, message="已有精修任务在运行。"))

        workspace = tailor_service.save_workspace(
            job,
            base_resume_path=request.form.get("base_resume_path", ""),
            role_markdown=request.form.get("role_markdown", ""),
            user_notes=request.form.get("user_notes", ""),
            session_instruction_text=request.form.get("instruction_text", ""),
        )
        next_step_key = tailor_service.next_step_key(workspace)
        if mode == "step" and step_key is None:
            step_key = tailor_service.current_step_key(workspace)
        if mode == "step" and step_key is None:
            return redirect(url_for("job_detail", job_id=job_id, message="当前没有可重跑的步骤。"))
        if mode == "next" and next_step_key is None:
            return redirect(url_for("job_detail", job_id=job_id, message="所有步骤都已完成。"))

        request_payload = json.dumps(
            {
                "job_id": job.id,
                "workspace_dir": str(workspace.workspace_dir),
                "base_resume_path": workspace.base_resume_path,
                "mode": mode,
                "step_key": step_key,
            },
            ensure_ascii=False,
        )
        reuse_latest_run = (
            latest_run is not None
            and latest_run.status != "running"
            and mode in {"next", "step"}
        )
        if reuse_latest_run:
            run = repository.update_tailor_run(
                latest_run.id or 0,
                workspace_dir=str(workspace.workspace_dir),
                base_resume_path=workspace.base_resume_path,
                status="pending",
                request_payload=request_payload,
                error_text="",
                started_at=None,
                finished_at=None,
                current_pid=None,
            )
        else:
            run = repository.create_tailor_run(
                TailorRun(
                    job_id=job.id or 0,
                    profile_slug=job.profile_slug,
                    workspace_dir=str(workspace.workspace_dir),
                    base_resume_path=workspace.base_resume_path,
                    session_id="",
                    status="pending",
                    request_payload=request_payload,
                )
            )

        if run is None:
            return redirect(url_for("job_detail", job_id=job_id, message="无法创建精修任务。"))

        worker = threading.Thread(
            target=run_tailor_task,
            args=(run.id or 0, job_id, mode, step_key),
            daemon=True,
            name=f"tailor-{job_id}-{run.id}",
        )
        worker.start()
        next_label = TAILOR_STEP_LABELS.get(step_key or next_step_key or "", "流水线")
        run_message = {
            "restart": "已从头启动精修流水线。",
            "step": f"已请求重跑 {TAILOR_STEP_LABELS.get(step_key or '', '当前步骤')}。",
            "next": f"已启动下一步：{next_label}。",
        }[mode]
        return redirect(url_for("job_detail", job_id=job_id, message=run_message))

    @web_app.post("/jobs/<int:job_id>/tailor/latex")
    def save_tailored_latex(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        workspace = tailor_service.save_tailored_resume(
            job,
            request.form.get("tailored_resume_text", ""),
        )
        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status != "running":
            sync_tailor_run_from_workspace(latest_run.id or 0, workspace)
        return redirect(url_for("job_detail", job_id=job_id, message="LaTeX 文本已保存。"))

    @web_app.post("/jobs/<int:job_id>/tailor/session/prompt")
    @web_app.post("/jobs/<int:job_id>/tailor/final-prompt")
    def run_tailor_final_prompt(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        workspace = tailor_service.ensure_workspace(job)
        raw_instruction_text = request.form.get("instruction_text")
        instruction_text = raw_instruction_text.strip() if raw_instruction_text is not None else ""
        prompt_source = "session_instruction_panel" if raw_instruction_text is not None else "manual"
        if raw_instruction_text is not None and not instruction_text:
            message = "右侧发送区为空，请先生成或填写要发给 Session 的内容。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=400)
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        if raw_instruction_text is not None:
            workspace = tailor_service.save_session_instruction(
                job,
                instruction_text=instruction_text,
            )
        if raw_instruction_text is None:
            instruction_text = workspace.session_instruction_text.strip()
            prompt_source = "session_instruction.md"
        if not instruction_text:
            instruction_text = workspace.revision_advice_text.strip()
            prompt_source = "resume_revision_advice.md"
        if not instruction_text:
            message = "当前没有可发送的修改建议，请先生成修改建议。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=400)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        latest_run = repository.latest_tailor_run_for_job(job_id)
        pipeline_state = tailor_service.load_pipeline_state(workspace)
        session_id = (
            latest_run.session_id
            if latest_run is not None and latest_run.session_id
            else str(pipeline_state.get("session_id") or "")
        )
        session_status = str(pipeline_state.get("session_status") or "not_started")
        if session_id and session_status == "not_started":
            session_status = "ready"
        if latest_run is not None and latest_run.status in ACTIVE_RUN_STATUSES:
            message = "已有精修任务在运行。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=409)
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        if session_status != "ready" or not session_id:
            message = "当前还没有可复用的 Codex session，请先建立 session。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=409)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        run = repository.create_tailor_run(
            TailorRun(
                job_id=job.id or 0,
                profile_slug=job.profile_slug,
                workspace_dir=str(workspace.workspace_dir),
                base_resume_path=workspace.base_resume_path,
                session_id=session_id,
                status="pending",
                current_step_key="session_prompt",
                request_payload=json.dumps(
                    {
                        "job_id": job.id,
                        "workspace_dir": str(workspace.workspace_dir),
                        "instruction_text": instruction_text,
                        "prompt_source": prompt_source,
                        "mode": "session_prompt",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        if run is None:
            message = "无法创建 Session Prompt 任务。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=500)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        worker = threading.Thread(
            target=run_final_prompt_task,
            args=(run.id or 0, job_id, instruction_text),
            daemon=True,
            name=f"tailor-session-prompt-{job_id}-{run.id}",
        )
        worker.start()
        if prompt_source in {"session_instruction_panel", "session_instruction.md"}:
            message = "已把右侧发送区内容发送给当前 Codex session。"
        elif prompt_source == "resume_revision_advice.md":
            message = "已把 resume_revision_advice.md 发送给当前 Codex session。"
        else:
            message = "已把本轮修改要求发送给当前 Codex session。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.get("/jobs/<int:job_id>/tailor/skills/<skill_key>")
    def tailor_skill_detail(job_id: int, skill_key: str):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        skill_path = tailor_service.skill_path(skill_key)
        if skill_path is None or not skill_path.exists():
            abort(404)
        skill_text = skill_path.read_text(encoding="utf-8")
        return render_template(
            "tailor_skill_detail.html",
            **build_shell_context(
                current_page="jobs",
                page_title=tailor_service.skill_label(skill_key),
                page_subtitle=f"{job.title} · {job.company}",
                page_sections=[
                    {"id": "skill-rendered", "label": "渲染预览"},
                    {"id": "skill-raw", "label": "原始文本"},
                ],
                page_eyebrow="Tailor Skill",
                page_badges=[skill_key, job_country_label(job)],
                message=request.args.get("message", ""),
            ),
            job=job,
            skill_key=skill_key,
            skill_label=tailor_service.skill_label(skill_key),
            skill_path=skill_path,
            skill_text=skill_text,
            skill_html=render_markdown_html(skill_text),
            open_finder_available=sys.platform == "darwin",
        )

    @web_app.post("/jobs/<int:job_id>/tailor/workspace/open-finder")
    def open_tailor_workspace_in_finder(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        workspace = tailor_service.ensure_workspace(job)
        if sys.platform != "darwin":
            message = "当前系统不支持 Finder 打开，仅 macOS 可用。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=400)
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        try:
            subprocess.run(["open", str(workspace.workspace_dir)], check=True)
        except Exception as exc:
            message = f"打开 Finder 失败：{exc}"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=500)
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        message = "已在 Finder 中打开当前工作区。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/skills/<skill_key>/reveal")
    def reveal_tailor_skill_in_finder(job_id: int, skill_key: str):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        skill_path = tailor_service.skill_path(skill_key)
        if skill_path is None or not skill_path.exists():
            abort(404)
        if sys.platform != "darwin":
            message = "当前系统不支持 Finder 定位，仅 macOS 可用。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=400)
            return redirect(url_for("tailor_skill_detail", job_id=job_id, skill_key=skill_key, message=message))
        try:
            subprocess.run(["open", "-R", str(skill_path)], check=True)
        except Exception as exc:
            message = f"定位文件失败：{exc}"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=500)
            return redirect(url_for("tailor_skill_detail", job_id=job_id, skill_key=skill_key, message=message))
        message = f"已在 Finder 中定位 {skill_path.name}。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("tailor_skill_detail", job_id=job_id, skill_key=skill_key, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/artifact/<artifact_key>/reveal")
    def reveal_tailor_artifact_in_finder(job_id: int, artifact_key: str):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        workspace = tailor_service.ensure_workspace(job)
        artifact_path = tailor_service.artifact_path(workspace, artifact_key)
        if artifact_path is None or not artifact_path.exists():
            abort(404)
        if sys.platform != "darwin":
            message = "当前系统不支持 Finder 定位，仅 macOS 可用。"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=400)
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        try:
            subprocess.run(["open", "-R", str(artifact_path)], check=True)
        except Exception as exc:
            message = f"定位文件失败：{exc}"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=500)
            return redirect(url_for("job_detail", job_id=job_id, message=message))
        message = f"已在 Finder 中定位 {artifact_path.name}。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.post("/jobs/<int:job_id>/tailor/final-latex")
    def save_final_latex(job_id: int):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)

        try:
            workspace = tailor_service.save_final_resume(
                job,
                request.form.get("final_resume_text", ""),
            )
        except Exception as exc:
            message = f"保存 final tex 失败：{exc}"
            if is_async_request():
                return json_message(message, payload=build_job_session_payload(job, message=message), status=500)
            return redirect(url_for("job_detail", job_id=job_id, message=message))

        latest_run = repository.latest_tailor_run_for_job(job_id)
        if latest_run is not None and latest_run.status != "running":
            sync_tailor_run_from_workspace(
                latest_run.id or 0,
                workspace,
                session_id=latest_run.session_id,
                last_message_override="已人工保存 final tex 并重新编译 PDF。",
            )
        message = "已保存 final tex，并重新编译 PDF。"
        if is_async_request():
            return json_message(message, payload=build_job_session_payload(job, message=message))
        return redirect(url_for("job_detail", job_id=job_id, message=message))

    @web_app.get("/jobs/<int:job_id>/tailor/artifact/<artifact_key>")
    def tailor_artifact(job_id: int, artifact_key: str):
        tailor_service = web_app.config["tailor_service"]
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        workspace = tailor_service.ensure_workspace(job)
        artifact_path = tailor_service.artifact_path(workspace, artifact_key)
        if artifact_path is None or not artifact_path.exists():
            abort(404)
        return send_file(artifact_path, conditional=True)

    @web_app.get("/api/jobs/<int:job_id>/tailor/session")
    def job_tailor_session_status(job_id: int):
        job = repository.get_job(job_id)
        if job is None:
            abort(404)
        return jsonify(build_job_session_payload(job))

    @web_app.get("/api/jobs")
    def api_jobs():
        profile_slug = request.args.get("profile_slug", "")
        min_score = request.args.get("min_score", default=45, type=int)
        location_query = request.args.get("location_query", "").strip()
        include_keywords = split_multiline_input(request.args.get("include_keywords", ""))
        exclude_keywords = split_multiline_input(request.args.get("exclude_keywords", ""))
        countries = normalize_selected_countries(request.args.getlist("countries"))
        jobs = repository.list_jobs(
            profile_slug=profile_slug or None,
            min_score=min_score,
            limit=200,
            countries=countries,
            location_query=location_query,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
        )
        return jsonify(
            [
                {
                    "id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "profile_slug": job.profile_slug,
                    "source_site": job.source_site,
                    "score": job.score,
                    "location_text": job.location_text,
                    "job_url": job.job_url,
                    "matched_keywords": job.matched_keywords,
                    "country_label": job_country_label(job),
                    "last_seen_at": job.last_seen_at.isoformat(),
                }
                for job in jobs
            ]
        )

    @web_app.get("/api/refresh-status")
    def refresh_status():
        refresh_state = web_app.config["refresh_state"]
        return jsonify(
            {
                "running": refresh_state["running"],
                "profile_slug": refresh_state["profile_slug"],
                "profile_label": refresh_state["profile_label"],
                "started_at": (
                    refresh_state["started_at"].isoformat()
                    if refresh_state["started_at"]
                    else None
                ),
                "finished_at": (
                    refresh_state["finished_at"].isoformat()
                    if refresh_state["finished_at"]
                    else None
                ),
                "last_result": refresh_state["last_result"],
                "last_trigger": refresh_state["last_trigger"],
            }
        )

    @web_app.get("/api/tailor-runs/<int:run_id>")
    def tailor_run_status(run_id: int):
        run = repository.get_tailor_run(run_id)
        if run is None:
            abort(404)

        job = repository.get_job(run.job_id)
        if job is None:
            abort(404)

        runtime = build_workspace_runtime(job)
        step_records = repository.list_tailor_run_steps(run_id)
        display_current_step_label = current_run_step_label(run, str(runtime["current_step_label"]))
        return jsonify(
            {
                "id": run.id,
                "job_id": run.job_id,
                "status": run.status,
                "stopped": run.status == "stopped",
                "error_text": run.error_text,
                "last_message": run.last_message,
                "session_id": run.session_id or runtime["session_id"],
                "session_status": runtime["session_status"],
                "session_established_at": runtime["session_established_at"],
                "session_error": runtime["session_error"],
                "current_pid": run.current_pid,
                "workspace_dir": run.workspace_dir,
                "workspace_label": runtime["workspace"].workspace_label,
                "pipeline_state": runtime["pipeline_state"],
                "pipeline_steps": runtime["pipeline_steps"],
                "step_records": [
                    {
                        "step_key": item.step_key,
                        "status": item.status,
                        "session_id": item.session_id,
                        "prompt_path": item.prompt_path,
                        "last_message_path": item.last_message_path,
                        "log_path": item.log_path,
                        "started_at": item.started_at.isoformat() if item.started_at else None,
                        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
                    }
                    for item in step_records
                ],
                "current_step_key": runtime["current_step_key"],
                "next_step_key": runtime["next_step_key"],
                "next_step_label": runtime["next_step_label"],
                "current_step_label": display_current_step_label,
                "completed_steps": runtime["completed_steps"],
                "current_step_log_text": runtime["current_step_log_text"],
                "matching_analysis_text": runtime["matching_analysis_text"],
                "tailored_resume_text": runtime["tailored_resume_text"],
                "fact_check_text": runtime["fact_check_text"],
                "final_resume_text": runtime["final_resume_text"],
                "diff_text": runtime["diff_text"],
                "vibe_review_text": runtime["vibe_review_text"],
                "artifact_urls": runtime["artifact_urls"],
                "pdf_urls": {
                    "final_pdf": runtime["artifact_urls"].get("final_pdf"),
                    "diff_pdf": runtime["artifact_urls"].get("diff_pdf"),
                },
                "pdf_ready": {
                    "final_pdf": runtime["final_pdf_ready"],
                    "diff_pdf": runtime["diff_pdf_ready"],
                },
                "artifacts": runtime["pipeline_state"].get("artifacts", {}),
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "updated_at": run.updated_at.isoformat() if run.updated_at else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "final_prompt_available": runtime["session_status"] == "ready"
                and bool(run.session_id or runtime["session_id"]),
            }
        )

    web_app.config["scheduler_started"] = False

    def shutdown_scheduler() -> None:
        if not web_app.config.get("scheduler_started"):
            return
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

    atexit.register(shutdown_scheduler)
    return web_app


def ensure_scheduler_started(web_app: Flask) -> None:
    if web_app.config.get("scheduler_started"):
        return
    scheduler = web_app.config["scheduler"]
    scheduler.start()
    web_app.config["scheduler_started"] = True


app = create_app()

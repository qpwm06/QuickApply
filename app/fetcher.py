from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser

from app.config import ROOT_DIR, SearchProfileConfig
from app.job_dedupe import build_job_dedupe_key

# 中文注释：每个站点单独调用 scrape_jobs 并行跑，互不拖累——
# 以前三个站点放在一次 scrape_jobs 里，Indeed 抛一个 SSLError 就会把 LinkedIn 已经抓到的结果一起丢掉。
# LinkedIn 失败时 jobspy 只打 ERROR 日志不抛异常，所以额外挂一个 logging handler 把它记成站点错误。
# 输出 {"rows": [...], "site_errors": {site: "一行错误"}}；超过 site_timeout_seconds 的站点记为超时。
JOBSPY_RUNNER = r"""
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, wait

from jobspy import scrape_jobs

payload = json.loads(sys.argv[1])
sites = list(payload["sites"])
site_timeout = float(payload.get("site_timeout_seconds") or 60)
logged_errors = {}


def site_key(name):
    return name.lower().replace("_", "").replace(" ", "")


class SiteErrorCollector(logging.Handler):
    def emit(self, record):
        if record.levelno < logging.ERROR:
            return
        name = record.name.split(":", 1)[-1]
        logged_errors.setdefault(site_key(name), record.getMessage().splitlines()[0][:300])


collector = SiteErrorCollector(level=logging.ERROR)
for logger_name in list(logging.root.manager.loggerDict):
    if logger_name.startswith("JobSpy"):
        logging.getLogger(logger_name).addHandler(collector)


def run_site(site):
    frame = scrape_jobs(
        site_name=[site],
        search_term=payload["search_term"],
        location=payload["location"],
        results_wanted=payload["results_wanted"],
        hours_old=payload["hours_old"],
        country_indeed=payload["country_indeed"],
        proxies=payload.get("proxies"),
        verbose=0,
    )
    return [] if frame is None else frame.to_dict(orient="records")


def short_error(exc):
    text = f"{type(exc).__name__}: {exc}".splitlines()[0]
    return text if len(text) <= 300 else text[:300] + "..."


pool = ThreadPoolExecutor(max_workers=max(1, len(sites)))
futures = {pool.submit(run_site, site): site for site in sites}
done, pending = wait(futures, timeout=site_timeout)
rows = []
site_errors = {}
for future in done:
    site = futures[future]
    try:
        site_rows = future.result()
    except Exception as exc:
        site_errors[site] = short_error(exc)
        continue
    rows.extend(site_rows)
    if not site_rows and site_key(site) in logged_errors:
        site_errors[site] = logged_errors[site_key(site)]
for future in pending:
    site_errors[futures[future]] = f"timed out after {site_timeout:.0f}s"

json.dump({"rows": rows, "site_errors": site_errors}, sys.stdout, default=str)
sys.stdout.flush()
# 中文注释：超时站点的线程还挂着，直接退出进程，不等它们。
os._exit(0)
"""


@dataclass(frozen=True)
class FetchedJob:
    unique_key: str
    search_term: str
    source_site: str
    title: str
    company: str
    location_text: str
    city: str
    state: str
    country: str
    job_url: str
    company_url: str
    interval: str
    currency: str
    min_amount: float | None
    max_amount: float | None
    is_remote: bool
    description: str
    date_posted: datetime | None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    # 中文注释：jobspy/pandas 的缺失值是 float NaN，直接 str() 会把 "nan" 存进数据库。
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "<na>", "nat"} else text


def _as_float(value: Any) -> float | None:
    if value in (None, "", "nan"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "remote"}


def _parse_date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return date_parser.parse(str(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _summarize_stderr(stderr: str) -> str:
    """中文注释：子进程崩溃时只保留最后一行（通常就是异常本身），不再把整段 INFO 日志和堆栈存进抓取记录。"""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    if not lines:
        return ""
    last_line = lines[-1]
    return last_line if len(last_line) <= 400 else last_line[:400] + "..."


def _split_runner_output(output: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    # 中文注释：兼容旧版 runner 直接输出 list 的格式。
    if isinstance(output, dict):
        rows = output.get("rows") or []
        site_errors = {
            str(site): str(message)
            for site, message in (output.get("site_errors") or {}).items()
        }
        return list(rows), site_errors
    return list(output or []), {}


def _to_proxy_url(raw_line: str) -> str:
    parts = raw_line.strip().split(":")
    if len(parts) != 4:
        raise ValueError("proxy line must be host:port:username:password")
    host, port, username, password = parts
    return f"http://{username}:{password}@{host}:{port}"


def load_proxy_urls(proxy_file: str | None) -> list[str]:
    if not proxy_file:
        return []
    file_path = (ROOT_DIR / proxy_file).resolve()
    if not file_path.exists():
        return []

    proxy_urls: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        proxy_urls.append(_to_proxy_url(raw))
    return proxy_urls


def _build_unique_key(
    source_site: str,
    title: str,
    company: str,
    location_text: str,
    job_url: str,
    *,
    city: str = "",
    state: str = "",
    country: str = "",
) -> str:
    _ = source_site, job_url
    # 中文注释：这里故意不把来源站点和 URL 放进 dedupe key。
    # 同岗跨 LinkedIn / Indeed / 同站不同链接时，需要先进入同一个合并桶。
    return build_job_dedupe_key(
        title=title,
        company=company,
        location_text=location_text,
        city=city,
        state=state,
        country=country,
    )


class JobSpyFetcher:
    def __init__(
        self,
        timeout_seconds: int = 75,
        proxy_file: str | None = "config/proxies.local.txt",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.proxy_urls = load_proxy_urls(proxy_file)

    _RETRY_DELAYS_SECONDS = (5, 15)
    # 中文注释：连续这么多条 query 都因网络错误（重试后仍失败）就判定断网，跳过剩余 query。
    _NETWORK_FAILURE_LIMIT = 2
    _RETRYABLE_HINTS = (
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "remote disconnected",
        "read timed out",
        "network is unreachable",
    )

    def _is_retryable_error(self, exc: BaseException) -> bool:
        if isinstance(exc, subprocess.TimeoutExpired):
            return True
        text = str(exc).lower()
        return any(hint in text for hint in self._RETRYABLE_HINTS)

    def _invoke_jobspy(
        self,
        profile: SearchProfileConfig,
        search_term: str,
        location: str,
    ) -> dict[str, Any]:
        payload = {
            "sites": profile.sites,
            "search_term": search_term,
            "location": location,
            "results_wanted": profile.results_wanted,
            "hours_old": profile.hours_old,
            "country_indeed": profile.country_indeed,
            "proxies": self.proxy_urls or None,
            # 中文注释：站点级超时比整个子进程超时短一点，保证慢站点被单独记超时，其他站点结果还能带回来。
            "site_timeout_seconds": max(10, self.timeout_seconds - 10),
        }
        result = subprocess.run(
            [sys.executable, "-c", JOBSPY_RUNNER, json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(_summarize_stderr(result.stderr) or "jobspy subprocess failed")
        if not result.stdout.strip():
            return {"rows": [], "site_errors": {}}
        return json.loads(result.stdout)

    def _run_query(
        self,
        profile: SearchProfileConfig,
        search_term: str,
        location: str,
    ) -> tuple[list[dict[str, Any]], int, list[str], dict[str, str]]:
        attempts = 0
        retry_errors: list[str] = []
        for attempt_index in range(len(self._RETRY_DELAYS_SECONDS) + 1):
            attempts += 1
            try:
                rows, site_errors = _split_runner_output(
                    self._invoke_jobspy(profile, search_term, location)
                )
                # 中文注释：所有站点都失败才算整条 query 失败，交给下面的重试逻辑；部分失败直接返回。
                requested_sites = set(profile.sites)
                if not rows and requested_sites and requested_sites <= set(site_errors):
                    raise RuntimeError(
                        "; ".join(f"{site}: {site_errors[site]}" for site in sorted(requested_sites))
                    )
                return rows, attempts - 1, retry_errors, site_errors
            except Exception as exc:
                if attempt_index >= len(self._RETRY_DELAYS_SECONDS) or not self._is_retryable_error(exc):
                    raise
                retry_errors.append(str(exc))
                time.sleep(self._RETRY_DELAYS_SECONDS[attempt_index])
        # 中文注释：理论上不可达，loop 内要么 return 要么 raise。
        raise RuntimeError("jobspy retry loop exited unexpectedly")

    def fetch_profile(
        self, profile: SearchProfileConfig
    ) -> tuple[list[FetchedJob], list[str], list[dict[str, Any]]]:
        jobs: list[FetchedJob] = []
        warnings: list[str] = []
        query_details: list[dict[str, Any]] = []
        consecutive_network_failures = 0
        network_down = False

        for search_term in profile.search_terms:
            for location in profile.locations:
                if network_down:
                    # 中文注释：网络已确认不可用（比如电脑休眠/断网时定时任务触发），剩余 query 直接跳过，
                    # 不再每条都等满 超时 × 重试 次数。
                    query_details.append(
                        {
                            "search_term": search_term,
                            "location": location,
                            "requested_sites": list(profile.sites),
                            "sites_seen": [],
                            "row_count": 0,
                            "status": "skipped",
                            "error": "skipped: network unavailable",
                            "retry_count": 0,
                            "retry_errors": [],
                            "site_errors": {},
                        }
                    )
                    continue
                try:
                    rows, retry_count, retry_errors, site_errors = self._run_query(
                        profile, search_term, location
                    )
                except Exception as exc:  # pragma: no cover - network path
                    error_text = str(exc)
                    warnings.append(
                        f"{profile.slug}: query={search_term!r}, location={location!r}, error={error_text}"
                    )
                    query_details.append(
                        {
                            "search_term": search_term,
                            "location": location,
                            "requested_sites": list(profile.sites),
                            "sites_seen": [],
                            "row_count": 0,
                            "status": "error",
                            "error": error_text,
                            "retry_count": len(self._RETRY_DELAYS_SECONDS),
                            "retry_errors": [],
                            "site_errors": {},
                        }
                    )
                    if self._is_retryable_error(exc):
                        consecutive_network_failures += 1
                        if consecutive_network_failures >= self._NETWORK_FAILURE_LIMIT:
                            network_down = True
                            warnings.append(
                                f"{profile.slug}: {consecutive_network_failures} consecutive queries failed with "
                                "network errors; skipped the remaining queries"
                            )
                    else:
                        consecutive_network_failures = 0
                    continue
                consecutive_network_failures = 0

                sites_seen = sorted(
                    {
                        _as_text(row.get("site") or row.get("SITE")).lower()
                        for row in rows
                        if _as_text(row.get("site") or row.get("SITE"))
                    }
                )
                query_details.append(
                    {
                        "search_term": search_term,
                        "location": location,
                        "requested_sites": list(profile.sites),
                        "sites_seen": sites_seen,
                        "row_count": len(rows),
                        "status": "partial" if site_errors else ("ok" if rows else "empty"),
                        "error": "",
                        "retry_count": retry_count,
                        "retry_errors": retry_errors,
                        "site_errors": site_errors,
                        "results_wanted": profile.results_wanted,
                    }
                )
                if retry_count:
                    warnings.append(
                        f"{profile.slug}: query={search_term!r}, location={location!r} succeeded after {retry_count} retr{'y' if retry_count == 1 else 'ies'}"
                    )
                for site, site_error in sorted(site_errors.items()):
                    warnings.append(
                        f"{profile.slug}: query={search_term!r}, location={location!r}, site={site} failed: {site_error}"
                    )

                if not rows:
                    continue

                for row in rows:
                    site = _as_text(row.get("site") or row.get("SITE"))
                    title = _as_text(row.get("title") or row.get("TITLE"))
                    company = _as_text(row.get("company") or row.get("COMPANY"))
                    location_text = _as_text(
                        row.get("location") or row.get("LOCATION")
                    )
                    city = _as_text(row.get("city") or row.get("CITY"))
                    state = _as_text(row.get("state") or row.get("STATE"))
                    country = _as_text(row.get("country") or row.get("COUNTRY"))
                    job_url = _as_text(row.get("job_url") or row.get("JOB_URL"))
                    company_url = _as_text(row.get("company_url"))
                    description = _as_text(
                        row.get("description") or row.get("DESCRIPTION")
                    )
                    interval = _as_text(row.get("interval") or row.get("INTERVAL"))
                    currency = _as_text(row.get("currency"))
                    is_remote = _as_bool(row.get("is_remote"))
                    min_amount = _as_float(
                        row.get("min_amount") or row.get("MIN_AMOUNT")
                    )
                    max_amount = _as_float(
                        row.get("max_amount") or row.get("MAX_AMOUNT")
                    )
                    date_posted = _parse_date(
                        row.get("date_posted") or row.get("DATE_POSTED")
                    )

                    if not title or not company:
                        continue

                    key = _build_unique_key(
                        site,
                        title,
                        company,
                        location_text or f"{city}, {state}",
                        job_url,
                        city=city,
                        state=state,
                        country=country,
                    )
                    jobs.append(
                        FetchedJob(
                        unique_key=key,
                        search_term=search_term,
                        source_site=site or "unknown",
                        title=title,
                        company=company,
                        location_text=location_text,
                        city=city,
                        state=state,
                        country=country,
                        job_url=job_url,
                        company_url=company_url,
                        interval=interval,
                        currency=currency,
                        min_amount=min_amount,
                        max_amount=max_amount,
                        is_remote=is_remote,
                        description=description,
                        date_posted=date_posted,
                    )
                    )

        return jobs, warnings, query_details

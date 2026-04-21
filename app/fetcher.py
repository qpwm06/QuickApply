from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dateutil import parser as date_parser

from app.config import ROOT_DIR, SearchProfileConfig

JOBSPY_RUNNER = r"""
import json
import sys

from jobspy import scrape_jobs

payload = json.loads(sys.argv[1])
frame = scrape_jobs(
    site_name=payload["sites"],
    search_term=payload["search_term"],
    location=payload["location"],
    results_wanted=payload["results_wanted"],
    hours_old=payload["hours_old"],
    country_indeed=payload["country_indeed"],
    proxies=payload.get("proxies"),
    verbose=0,
)
rows = [] if frame is None else frame.to_dict(orient="records")
json.dump(rows, sys.stdout, default=str)
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
    return str(value).strip()


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
) -> str:
    stable_text = "|".join(
        [
            source_site.lower(),
            title.lower(),
            company.lower(),
            location_text.lower(),
            job_url.lower(),
        ]
    )
    return hashlib.sha1(stable_text.encode("utf-8")).hexdigest()


class JobSpyFetcher:
    def __init__(
        self,
        timeout_seconds: int = 75,
        proxy_file: str | None = "config/proxies.local.txt",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.proxy_urls = load_proxy_urls(proxy_file)

    def _run_query(
        self,
        profile: SearchProfileConfig,
        search_term: str,
        location: str,
    ) -> list[dict[str, Any]]:
        payload = {
            "sites": profile.sites,
            "search_term": search_term,
            "location": location,
            "results_wanted": profile.results_wanted,
            "hours_old": profile.hours_old,
            "country_indeed": profile.country_indeed,
            "proxies": self.proxy_urls or None,
        }
        result = subprocess.run(
            [sys.executable, "-c", JOBSPY_RUNNER, json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "jobspy subprocess failed")
        if not result.stdout.strip():
            return []
        return json.loads(result.stdout)

    def fetch_profile(
        self, profile: SearchProfileConfig
    ) -> tuple[list[FetchedJob], list[str], list[dict[str, Any]]]:
        jobs_by_key: dict[str, FetchedJob] = {}
        warnings: list[str] = []
        query_details: list[dict[str, Any]] = []

        for search_term in profile.search_terms:
            for location in profile.locations:
                try:
                    rows = self._run_query(profile, search_term, location)
                except Exception as exc:  # pragma: no cover - network path
                    warning_text = (
                        f"{profile.slug}: query={search_term!r}, location={location!r}, error={exc}"
                    )
                    warnings.append(warning_text)
                    query_details.append(
                        {
                            "search_term": search_term,
                            "location": location,
                            "requested_sites": list(profile.sites),
                            "sites_seen": [],
                            "row_count": 0,
                            "status": "error",
                            "error": str(exc),
                        }
                    )
                    continue

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
                        "status": "ok" if rows else "empty",
                        "error": "",
                    }
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
                    )
                    jobs_by_key[key] = FetchedJob(
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

        return list(jobs_by_key.values()), warnings, query_details

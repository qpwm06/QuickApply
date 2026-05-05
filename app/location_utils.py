from __future__ import annotations

from collections.abc import Iterable
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from app.models import JobRecord

COUNTRY_FILTER_OPTIONS = ("China", "USA", "Other", "Unknown")
SOURCE_SITE_URLS = {
    "linkedin": "https://www.linkedin.com/jobs/",
    "indeed": "https://www.indeed.com/",
    "zip_recruiter": "https://www.ziprecruiter.com/jobs-search",
}
US_STATE_TOKENS = (
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "dc",
    "al",
    "ak",
    "az",
    "ar",
    "ca",
    "co",
    "ct",
    "de",
    "fl",
    "ga",
    "hi",
    "id",
    "il",
    "in",
    "ia",
    "ks",
    "ky",
    "la",
    "me",
    "md",
    "ma",
    "mi",
    "mn",
    "ms",
    "mo",
    "mt",
    "ne",
    "nv",
    "nh",
    "nj",
    "nm",
    "ny",
    "nc",
    "nd",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "vt",
    "va",
    "wa",
    "wv",
    "wi",
    "wy",
)
US_STATE_PATTERN = re.compile(r"\b(" + "|".join(re.escape(token) for token in US_STATE_TOKENS) + r")\b")


def infer_country_label(
    *,
    country: str = "",
    location_text: str = "",
    city: str = "",
    state: str = "",
) -> str:
    blob = " ".join([country, location_text, city, state]).strip().lower()
    if not blob:
        return "Unknown"

    china_tokens = (
        "china",
        "beijing",
        "shanghai",
        "shenzhen",
        "guangzhou",
        "hong kong",
        "hong kong sar",
    )
    if any(token in blob for token in china_tokens):
        return "China"

    usa_tokens = (
        "usa",
        "united states",
        "us",
    )
    if state.strip() or any(token in blob for token in usa_tokens) or US_STATE_PATTERN.search(blob):
        return "USA"

    return "Other"


def job_country_label(job: JobRecord) -> str:
    return infer_country_label(
        country=job.country,
        location_text=job.location_text,
        city=job.city,
        state=job.state,
    )


def source_site_home_url(source_site: str) -> str:
    return SOURCE_SITE_URLS.get(source_site.strip().lower(), "")


def linkedin_jobs_search_url(keywords: str, location: str = "") -> str:
    params: dict[str, str] = {}
    normalized_keywords = " ".join(keywords.split())
    normalized_location = " ".join(location.split())
    if normalized_keywords:
        params["keywords"] = normalized_keywords
    if normalized_location:
        params["location"] = normalized_location
    query = urlencode(params)
    if not query:
        return "https://www.linkedin.com/jobs/search/"
    return f"https://www.linkedin.com/jobs/search/?{query}"


def extract_linkedin_job_id(url: str) -> str:
    normalized_url = url.strip()
    if not normalized_url:
        return ""

    url_parts = urlsplit(normalized_url)
    for key, value in parse_qsl(url_parts.query, keep_blank_values=True):
        if key == "currentJobId" and value.strip():
            return value.strip()

    match = re.search(r"/jobs/view/([^/?#]+)", url_parts.path)
    if match:
        return match.group(1).strip()
    return ""


def _linkedin_search_location(job: JobRecord) -> str:
    if job.location_text.strip():
        return " ".join(job.location_text.split())

    deduped_parts: list[str] = []
    seen: set[str] = set()
    for value in (job.city, job.state, job.country):
        normalized_value = " ".join(value.split())
        if not normalized_value:
            continue
        lowered = normalized_value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped_parts.append(normalized_value)
    return ", ".join(deduped_parts)


def linkedin_job_detail_shell_url(job: JobRecord) -> str:
    # 中文注释：以前用 /jobs/search/?keywords=...&currentJobId=... 拼"搜索壳页"，想保留双栏体验。
    # 但 LinkedIn 前端在搜索结果异步加载完之后会强制把右栏切到搜索结果第一条，覆盖 currentJobId，
    # 表现为"打开瞬间正确，几秒后跳到另一条"。改成 /jobs/view/<id>/ 标准详情页，不再被搜索结果干扰。
    if job.source_site.strip().lower() != "linkedin":
        return ""

    current_job_id = extract_linkedin_job_id(job.job_url)
    if not current_job_id:
        return ""

    return f"https://www.linkedin.com/jobs/view/{current_job_id}/"


def matches_location_query(job: JobRecord, location_query: str) -> bool:
    query = " ".join(location_query.lower().split())
    if not query:
        return True

    haystack = " ".join(
        [
            job.location_text,
            job.city,
            job.state,
            job.country,
            "Remote" if job.is_remote else "",
        ]
    ).lower()
    return query in haystack


def normalize_selected_countries(values: Iterable[str] | None) -> list[str]:
    selected = [value for value in (values or []) if value in COUNTRY_FILTER_OPTIONS]
    return selected or ["China", "USA"]

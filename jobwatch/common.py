"""공통 유틸: HTTP 세션, Job 모델, HTML→텍스트."""
from __future__ import annotations

import html
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("jobwatch")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
    return s


@dataclass
class Job:
    company: str
    job_id: str  # 회사 내 고유 ID
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    team: str = ""
    posted_at: str | None = None  # ISO date (YYYY-MM-DD)
    description: str = ""  # 평문 JD. 상세 수집 전에는 빈 문자열

    @property
    def key(self) -> str:
        return f"{self.company}:{self.job_id}"


_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|section)[^>]*>", re.I)


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)  # greenhouse는 이중 이스케이프
    s = _BLOCK.sub("\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def iso_date(v) -> str | None:
    """epoch(초/ms), ISO 문자열, 'September 26, 2026' 같은 값을 YYYY-MM-DD로."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        if v > 1e12:
            v /= 1000
        return datetime.fromtimestamp(v, timezone.utc).date().isoformat()
    v = str(v).strip()
    m = re.match(r"\d{4}-\d{2}-\d{2}", v)
    if m:
        return m.group(0)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def polite_sleep(sec: float = 0.3) -> None:
    time.sleep(sec)

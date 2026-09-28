"""회사별 수집기.

각 Source는
  - list_jobs(): 대상 직무 후보 목록 (가능하면 JD 포함)
  - fetch_detail(job): JD가 비어 있는 경우 상세 페이지에서 채움
를 제공한다. 상세 수집은 DB에 JD가 없는 신규 공고에만 실행된다.
"""
from __future__ import annotations

import json
import os
import re
from urllib.parse import quote

from .common import Job, html_to_text, iso_date, log, polite_sleep, session


class Source:
    company: str = ""
    detail_workers: int = 6  # 상세 페이지 동시 요청 수

    def __init__(self):
        self.s = session()

    def list_jobs(self) -> list[Job]:
        raise NotImplementedError

    def fetch_detail(self, job: Job) -> Job:
        return job


# ---------------------------------------------------------------- Greenhouse
class Greenhouse(Source):
    def __init__(self, company: str, board: str):
        super().__init__()
        self.company, self.board = company, board

    def list_jobs(self):
        r = self.s.get(f"https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs?content=true", timeout=60)
        r.raise_for_status()
        out = []
        for j in r.json()["jobs"]:
            out.append(Job(
                company=self.company,
                job_id=str(j["id"]),
                title=j["title"].strip(),
                url=j["absolute_url"],
                locations=[j.get("location", {}).get("name", "")],
                team=", ".join(d["name"] for d in j.get("departments", [])),
                posted_at=iso_date(j.get("first_published") or j.get("updated_at")),
                description=html_to_text(j.get("content")),
            ))
        return out


# ---------------------------------------------------------------- Ashby
class Ashby(Source):
    def __init__(self, company: str, board: str):
        super().__init__()
        self.company, self.board = company, board

    def list_jobs(self):
        r = self.s.get(f"https://api.ashbyhq.com/posting-api/job-board/{self.board}", timeout=60)
        r.raise_for_status()
        out = []
        for j in r.json()["jobs"]:
            if not j.get("isListed", True):
                continue
            locs = [j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []]
            out.append(Job(
                company=self.company,
                job_id=j["id"],
                title=j["title"].strip(),
                url=j["jobUrl"],
                locations=[l for l in locs if l],
                team=" / ".join(x for x in (j.get("department"), j.get("team")) if x),
                posted_at=iso_date(j.get("publishedAt")),
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            ))
        return out


# ---------------------------------------------------------------- Workday (Nvidia)
class Workday(Source):
    def __init__(self, company: str, host: str, tenant: str, site: str):
        super().__init__()
        self.company = company
        self.base = f"https://{host}/wday/cxs/{tenant}/{site}"
        self.public = f"https://{host}/en-US/{site}"

    # Workday 검색은 2000건에서 잘리므로 직군(jobFamilyGroup) 패싯별로 나눠 받는다
    FAMILIES = ("Engineering", "Research", "Univ Employment", "IT - Information Technology")

    def _search(self, facets: dict, offset: int) -> dict:
        r = self.s.post(
            f"{self.base}/jobs",
            json={"appliedFacets": facets, "limit": 20, "offset": offset, "searchText": ""},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()

    def list_jobs(self):
        first = self._search({}, 0)
        fam = next((f for f in first.get("facets", []) if f["facetParameter"] == "jobFamilyGroup"), {"values": []})
        ids = [v["id"] for v in fam["values"] if v["descriptor"] in self.FAMILIES]
        seen: dict[str, Job] = {}
        for fid in ids:
            offset, total = 0, None
            while total is None or offset < min(total, 2000):
                d = self._search({"jobFamilyGroup": [fid]}, offset)
                if total is None:
                    total = d.get("total", 0)  # Workday는 첫 페이지에서만 total을 준다
                posts = d.get("jobPostings", [])
                if not posts:
                    break
                for p in posts:
                    path = p["externalPath"]
                    jid = (p.get("bulletFields") or [path.rsplit("_", 1)[-1]])[0]
                    seen.setdefault(jid, Job(
                        company=self.company,
                        job_id=jid,
                        title=p["title"].strip(),
                        url=self.public + path,
                        locations=[p.get("locationsText", "")],
                    ))
                offset += 20
                polite_sleep(0.2)
        return list(seen.values())

    def fetch_detail(self, job):
        path = job.url[len(self.public):]
        r = self.s.get(self.base + path, timeout=60)
        r.raise_for_status()
        info = r.json()["jobPostingInfo"]
        job.description = html_to_text(info.get("jobDescription"))
        job.posted_at = iso_date(info.get("startDate")) or job.posted_at
        locs = [info.get("location")] + (info.get("additionalLocations") or [])
        job.locations = [l for l in locs if l] or job.locations
        return job


# ---------------------------------------------------------------- Eightfold PCSX (Microsoft, Netflix)
class Eightfold(Source):
    detail_workers = 2  # Microsoft는 동시 요청이 많으면 429

    def __init__(self, company: str, host: str, domain: str, queries: list[str]):
        super().__init__()
        self.company, self.host, self.domain, self.queries = company, host, domain, queries

    def list_jobs(self):
        seen: dict[str, Job] = {}
        for q in self.queries:
            start, count = 0, None
            while count is None or start < count:
                r = self.s.get(
                    f"https://{self.host}/api/pcsx/search",
                    params={"domain": self.domain, "query": q, "start": start},
                    timeout=60,
                )
                r.raise_for_status()
                d = r.json()["data"]
                count = d.get("count", 0)
                pos = d.get("positions", [])
                if not pos:
                    break
                for p in pos:
                    jid = str(p["id"])
                    if jid in seen:
                        continue
                    seen[jid] = Job(
                        company=self.company,
                        job_id=jid,
                        title=p["name"].strip(),
                        url=f"https://{self.host}" + (p.get("positionUrl") or f"/careers/job/{jid}"),
                        locations=p.get("standardizedLocations") or p.get("locations") or [],
                        team=p.get("department") or "",
                        posted_at=iso_date(p.get("postedTs") or p.get("creationTs")),
                    )
                start += len(pos)
                polite_sleep(0.2)
        return list(seen.values())

    def fetch_detail(self, job):
        polite_sleep(0.5)
        r = self.s.get(
            f"https://{self.host}/api/pcsx/position_details",
            params={"position_id": job.job_id, "domain": self.domain, "hl": "en"},
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()["data"]
        job.description = html_to_text(d.get("jobDescription"))
        if d.get("publicUrl"):
            job.url = d["publicUrl"]
        return job


# ---------------------------------------------------------------- Amazon
class Amazon(Source):
    company = "Amazon"
    CATEGORIES = ["software-development", "machine-learning-science", "research-science", "data-science"]

    def list_jobs(self):
        seen: dict[str, Job] = {}
        for cat in self.CATEGORIES:
            offset, hits = 0, None
            while hits is None or offset < hits:
                r = self.s.get(
                    "https://www.amazon.jobs/en/search.json",
                    params={"category[]": cat, "result_limit": 100, "offset": offset, "sort": "recent"},
                    timeout=60,
                )
                r.raise_for_status()
                d = r.json()
                hits = d.get("hits", 0)
                jobs = d.get("jobs", [])
                if not jobs:
                    break
                for j in jobs:
                    jid = str(j["id_icims"])
                    if jid in seen:
                        continue
                    desc = "\n".join(
                        html_to_text(j.get(k)) for k in ("description", "basic_qualifications", "preferred_qualifications")
                    )
                    seen[jid] = Job(
                        company=self.company,
                        job_id=jid,
                        title=j["title"].strip(),
                        url="https://www.amazon.jobs" + j["job_path"],
                        locations=[j.get("normalized_location") or j.get("location") or ""],
                        team=(j.get("team") or {}).get("label", "") if isinstance(j.get("team"), dict) else (j.get("job_category") or ""),
                        posted_at=iso_date(j.get("posted_date")),
                        description=desc,
                    )
                offset += len(jobs)
                polite_sleep(0.2)
                if offset >= 10000:  # amazon.jobs 검색 상한
                    break
        return list(seen.values())


# ---------------------------------------------------------------- Google
class Google(Source):
    company = "Google"
    QUERIES = ["software engineer", "machine learning", "research scientist", "site reliability engineer"]
    _AF = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(.*?), sideChannel: \{\}\}\);", re.S)

    def list_jobs(self):
        seen: dict[str, Job] = {}
        for q in self.QUERIES:
            page, total = 1, None
            while total is None or (page - 1) * 20 < total:
                r = self.s.get(
                    "https://www.google.com/about/careers/applications/jobs/results",
                    params={"q": q, "page": page},
                    timeout=60,
                )
                r.raise_for_status()
                m = self._AF.search(r.text)
                if not m:
                    log.warning("google: 데이터 블록 없음 (q=%s page=%s)", q, page)
                    break
                data = json.loads(m.group(1))
                rows = data[0] or []
                total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
                if not rows:
                    break
                for x in rows:
                    jid = str(x[0])
                    if jid in seen:
                        continue
                    slug = re.sub(r"[^a-z0-9]+", "-", x[1].lower()).strip("-")
                    desc = "\n".join(html_to_text(x[i][1]) for i in (10, 3, 4) if isinstance(x[i], list) and len(x[i]) > 1)
                    seen[jid] = Job(
                        company=self.company,
                        job_id=jid,
                        title=x[1].strip(),
                        url=f"https://www.google.com/about/careers/applications/jobs/results/{jid}-{slug}",
                        locations=[l[0] for l in (x[9] or [])],
                        team=x[7] or "",
                        posted_at=iso_date(x[12][0]) if isinstance(x[12], list) else None,
                        description=desc,
                    )
                page += 1
                polite_sleep(0.3)
        return list(seen.values())


# ---------------------------------------------------------------- Apple
class Apple(Source):
    company = "Apple"
    # jobs.apple.com 서브팀 코드: Software & Services + Machine Learning & AI
    TEAMS = [
        "SFTWR-AF", "SFTWR-CLD", "SFTWR-COS", "SFTWR-DSR", "SFTWR-ISTECH", "SFTWR-MCHLN",
        "SFTWR-SEC", "SFTWR-SQAT", "SFTWR-WSFT", "MLAI-MLI", "MLAI-DLRL", "MLAI-NLP", "MLAI-CV",
    ]
    _HYD = re.compile(r"__staticRouterHydrationData\s*=\s*JSON\.parse\((\".*?\")\);", re.S)

    def _hydrate(self, url, params=None):
        r = self.s.get(url, params=params, timeout=60)
        r.raise_for_status()
        m = self._HYD.search(r.text)
        if not m:
            raise RuntimeError(f"apple: hydration 데이터 없음 {url}")
        return json.loads(json.loads(m.group(1)))["loaderData"]

    def list_jobs(self):
        seen: dict[str, Job] = {}
        for team in self.TEAMS:
            page, total = 1, None
            while total is None or (page - 1) * 20 < total:
                s = self._hydrate("https://jobs.apple.com/en-us/search", {"team": f"x-{team}", "page": page})["search"]
                total = s.get("totalRecords", 0)
                rows = s.get("searchResults") or []
                if not rows or total > 5000:  # 필터가 안 먹힌 경우(전체 공고) 방어
                    break
                for x in rows:
                    jid = x["positionId"]
                    if jid in seen:
                        continue
                    seen[jid] = Job(
                        company=self.company,
                        job_id=jid,
                        title=x["postingTitle"].strip(),
                        url=f"https://jobs.apple.com/en-us/details/{jid}/{x.get('transformedPostingTitle', '')}",
                        locations=[l.get("name", "") for l in x.get("locations", [])],
                        team=(x.get("team") or {}).get("teamName", ""),
                        posted_at=iso_date(x.get("postDateInGMT") or x.get("postingDate")),
                    )
                page += 1
                polite_sleep(0.3)
        return list(seen.values())

    def fetch_detail(self, job):
        d = self._hydrate(job.url)["jobDetails"]["jobsData"]
        job.description = "\n".join(
            html_to_text(d.get(k)) for k in ("jobSummary", "description", "minimumQualifications", "preferredQualifications")
        )
        return job


# ---------------------------------------------------------------- Oracle (HCM Cloud)
class Oracle(Source):
    company = "Oracle"
    BASE = "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest"
    SITE = "CX_45001"
    QUERIES = ["software", "machine learning", "data scientist", "site reliability", "cloud engineer", "AI"]

    def list_jobs(self):
        seen: dict[str, Job] = {}
        for q in self.QUERIES:
            offset, total = 0, None
            while total is None or offset < total:
                finder = f'findReqs;siteNumber={self.SITE},limit=200,offset={offset},keyword="{q}",sortBy=POSTING_DATES_DESC'
                r = self.s.get(
                    f"{self.BASE}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder={quote(finder, safe=';=,')}",
                    timeout=90,
                )
                r.raise_for_status()
                it = r.json()["items"][0]
                total = it.get("TotalJobsCount", 0)
                reqs = it.get("requisitionList") or []
                if not reqs:
                    break
                for x in reqs:
                    jid = str(x["Id"])
                    if jid in seen:
                        continue
                    seen[jid] = Job(
                        company=self.company,
                        job_id=jid,
                        title=x["Title"].strip(),
                        url=f"https://careers.oracle.com/jobs/#en/sites/jobsearch/job/{jid}",
                        locations=[x.get("PrimaryLocation") or ""],
                        team=x.get("JobFamily") or "",
                        posted_at=iso_date(x.get("PostedDate")),
                    )
                offset += len(reqs)
                polite_sleep(0.3)
        return list(seen.values())

    def fetch_detail(self, job):
        finder = f'ById;Id="{job.job_id}",siteNumber={self.SITE}'
        r = self.s.get(
            f"{self.BASE}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder={quote(finder, safe=';=,')}",
            timeout=60,
        )
        r.raise_for_status()
        items = r.json().get("items") or []
        if items:
            d = items[0]
            job.description = "\n".join(
                html_to_text(d.get(k)) for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")
            )
            job.team = d.get("Organization") or d.get("JobFamily") or job.team
        return job


# ---------------------------------------------------------------- Netflix (Eightfold v2)
class Netflix(Source):
    company = "Netflix"
    HOST = "https://explore.jobs.netflix.net"

    def list_jobs(self):
        out, start, count = [], 0, None
        while count is None or start < count:
            r = self.s.get(f"{self.HOST}/api/apply/v2/jobs", params={"domain": "netflix.com", "num": 50, "start": start}, timeout=60)
            r.raise_for_status()
            d = r.json()
            count = d.get("count", 0)
            pos = d.get("positions", [])
            if not pos:
                break
            for p in pos:
                out.append(Job(
                    company=self.company,
                    job_id=str(p["id"]),
                    title=p["name"].strip(),
                    url=p.get("canonicalPositionUrl") or f"{self.HOST}/careers/job/{p['id']}",
                    locations=p.get("locations") or [p.get("location", "")],
                    team=p.get("department") or "",
                    posted_at=iso_date(p.get("t_create")),
                ))
            start += len(pos)
            polite_sleep(0.2)
        return out

    def fetch_detail(self, job):
        r = self.s.get(f"{self.HOST}/api/apply/v2/jobs/{job.job_id}", params={"domain": "netflix.com"}, timeout=60)
        r.raise_for_status()
        job.description = html_to_text(r.json().get("job_description"))
        return job


# ---------------------------------------------------------------- Meta (브라우저 렌더링 필요)
CHROME = os.environ.get(
    "JOBWATCH_CHROME", os.path.expanduser("~/.cache/ms-playwright/chromium-1107/chrome-linux/chrome")
)


class Meta(Source):
    """metacareers.com은 일반 HTTP 요청을 차단하므로 헤드리스 Chromium으로 GraphQL 응답을 가로챈다."""

    company = "Meta"
    QUERIES = ["software engineer", "machine learning", "research scientist", "engineer"]

    def __init__(self):
        super().__init__()
        self._pw = self._browser = None

    def _page(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        return self._browser.new_page()

    def close(self):
        if self._browser:
            self._browser.close()
            self._pw.stop()
            self._browser = self._pw = None

    def list_jobs(self):
        seen: dict[str, Job] = {}
        page = self._page()
        batch: list[dict] = []

        def on_resp(resp):
            if "graphql" not in resp.url:
                return
            try:
                d = resp.json()
            except Exception:
                return
            jobs = (((d or {}).get("data") or {}).get("job_search_with_featured_jobs_v2") or {}).get("all_jobs")
            if jobs:
                batch.extend(jobs)

        page.on("response", on_resp)
        try:
            for q in self.QUERIES:
                batch.clear()
                page.goto(f"https://www.metacareers.com/jobs?q={quote(q)}", wait_until="networkidle", timeout=90000)
                page.wait_for_timeout(1500)
                log.info("meta: q=%r -> %d", q, len(batch))
                for x in batch:
                    jid = str(x["id"])
                    if jid in seen:
                        continue
                    seen[jid] = Job(
                        company=self.company,
                        job_id=jid,
                        title=x["title"].strip(),
                        url=f"https://www.metacareers.com/profile/job_details/{jid}",
                        locations=x.get("locations") or [],
                        team=", ".join((x.get("teams") or []) + (x.get("sub_teams") or [])),
                    )
        finally:
            page.close()
        return list(seen.values())

    def fetch_detail(self, job):
        page = self._page()
        try:
            page.goto(job.url, wait_until="networkidle", timeout=90000)
            text = page.inner_text("body")
        finally:
            page.close()
        # 헤더 네비게이션/푸터 잘라내기: "Apply now" 이후 ~ 푸터 이전
        if "Apply now" in text:
            text = text.split("Apply now", 1)[1]
        for stop in ("\nMeta is proud to be an Equal", "\nEqual Employment Opportunity", "\nLocations\n"):
            if stop in text:
                text = text.split(stop, 1)[0]
        job.description = text.strip()
        return job


def all_sources() -> list[Source]:
    return [
        Meta(),
        Greenhouse("Anthropic", "anthropic"),
        Workday("Nvidia", "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"),
        Google(),
        Ashby("OpenAI", "openai"),
        Greenhouse("SpaceX", "spacex"),
        Apple(),
        Amazon(),
        Netflix(),
        Oracle(),
        Eightfold(
            "Microsoft", "apply.careers.microsoft.com", "microsoft.com",
            ["software engineer", "machine learning", "applied scientist", "research scientist",
             "data scientist", "site reliability", "AI engineer", "developer"],
        ),
    ]

"""수집 실행: 목록 → 직무 필터 → (신규만) 상세 → 분류/스킬 추출 → DB."""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import time
from collections import Counter
from datetime import date

from . import db
from .classify import is_target, level_of, min_years, track_of
from .common import Job, log
from .skills import extract
from .sources import Meta, Source, all_sources

# 목록이 직전 활성 공고 수의 이 비율 미만이면 사이트 장애로 보고 마감 처리를 건너뜀
CLOSE_GUARD = 0.5


def annotate(job: Job) -> dict:
    text = f"{job.title}\n{job.description}"
    return {
        "track": track_of(job.title, job.team),
        "level": level_of(job.title),
        "min_yoe": min_years(job.description),
        "skills": extract(text),
    }


def run_source(src: Source, known: dict[str, str], max_details: int | None) -> tuple[list[Job], int]:
    t0 = time.time()
    listed = src.list_jobs()
    targets = [j for j in listed if is_target(j.title)]
    need = []
    for j in targets:
        if not j.description and known.get(j.key):
            j.description = known[j.key]  # 이미 받아둔 JD 재사용
        if not j.description:
            need.append(j)
    if max_details is not None:
        need = need[:max_details]
    log.info("%s: listed=%d targets=%d need_detail=%d", src.company, len(listed), len(targets), len(need))

    def detail(j):
        try:
            return src.fetch_detail(j)
        except Exception as e:  # 상세 하나 실패해도 계속
            log.warning("%s detail %s 실패: %s", src.company, j.job_id, e)
            return j

    if isinstance(src, Meta):  # playwright sync API는 단일 스레드
        for i, j in enumerate(need):
            detail(j)
            if i % 50 == 0:
                log.info("meta detail %d/%d", i, len(need))
        src.close()
    else:
        with cf.ThreadPoolExecutor(src.detail_workers) as ex:
            list(ex.map(detail, need))
    log.info("%s: done in %.0fs", src.company, time.time() - t0)
    return targets, len(listed)


def collect(db_path: str, only: list[str] | None = None, max_details: int | None = None) -> None:
    conn = db.connect(db_path)
    known = db.known_descriptions(conn)
    today = date.today().isoformat()
    sources = [s for s in all_sources() if not only or s.company.lower() in {o.lower() for o in only}]

    with cf.ThreadPoolExecutor(len(sources) or 1) as ex:
        futs = {ex.submit(run_source, s, known, max_details): s for s in sources}
        for fut in cf.as_completed(futs):
            src = futs[fut]
            try:
                targets, listed = fut.result()
            except Exception as e:
                log.exception("%s 수집 실패", src.company)
                conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (today, src.company, 0, 0, 0, 0, repr(e)[:500]))
                conn.commit()
                continue
            prev_active = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE company=? AND active=1", (src.company,)
            ).fetchone()[0]
            new = sum(db.upsert(conn, j, annotate(j), today) for j in targets)
            closed = 0
            if targets and len(targets) >= CLOSE_GUARD * prev_active:
                closed = db.close_missing(conn, src.company, {j.key for j in targets}, today)
            conn.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (today, src.company, listed, len(targets), new, closed, None)
            )
            conn.commit()
            log.info("%s: +%d new, -%d closed", src.company, new, closed)

    rescore(conn)
    db.write_snapshot(conn, today)
    conn.commit()
    conn.close()


_SENT = re.compile(r"\n+|(?<=[.!?])\s+(?=[A-Z])")
BOILERPLATE_SHARE = 0.2  # 한 회사 JD의 20% 이상에 똑같이 나오는 문장은 회사 소개/복지/EEO 문구로 보고 제외


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in _SENT.split(text or "") if len(x.strip()) > 20]


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def rescore(conn) -> None:
    """회사별 공통 문구를 걸러낸 JD로 트랙/레벨/경력/스킬을 다시 계산."""
    rows = conn.execute("SELECT key, company, title, team, description FROM jobs").fetchall()
    by_co: dict[str, list] = {}
    for r in rows:
        by_co.setdefault(r["company"], []).append(r)
    for company, rs in by_co.items():
        freq = Counter()
        for r in rs:
            freq.update({_norm(x) for x in _sentences(r["description"])})
        n_desc = sum(1 for r in rs if r["description"])
        cut = max(5, BOILERPLATE_SHARE * n_desc)
        common = {k for k, v in freq.items() if v >= cut}
        for r in rs:
            desc = r["description"] or ""
            core = "\n".join(x for x in _sentences(desc) if _norm(x) not in common)
            conn.execute(
                "UPDATE jobs SET track=?, level=?, min_yoe=?, skills=?, active=CASE WHEN ? THEN active ELSE 0 END WHERE key=?",
                (track_of(r["title"], r["team"] or ""), level_of(r["title"]), min_years(desc),
                 json.dumps(extract(f"{r['title']}\n{core}")), is_target(r["title"]), r["key"]),
            )
        log.info("%s: 공통 문구 %d개 제외", company, len(common))


def reannotate(db_path: str) -> None:
    """분류 규칙/스킬 사전을 고친 뒤 저장된 JD에 다시 적용."""
    conn = db.connect(db_path)
    rescore(conn)
    db.write_snapshot(conn, date.today().isoformat())
    conn.commit()
    conn.close()

"""DB → 정적 사이트.

site/
  index.html                  대시보드 앱 (버전 선택 가능)
  reports/index.json          버전 목록 (최신이 앞)
  reports/<YYYY-MM-DD>/data.json.gz   그 날의 리포트 데이터 (하루 한 버전, 같은 날 재실행은 덮어씀)
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path

from . import db
from .classify import TRACKS
from .skills import SKILLS

COMPANY_ORDER = ["Meta", "Anthropic", "Nvidia", "Google", "OpenAI", "SpaceX",
                 "Apple", "Amazon", "Netflix", "Oracle", "Microsoft"]
LEVELS = ["Intern/New Grad", "Junior", "Mid", "Senior", "Staff", "Principal+", "Eng Manager", "Unspecified"]


def build(db_path: str, site_dir: str) -> str:
    conn = db.connect(db_path)
    skills = [n for _, n, _ in SKILLS]
    cats = [c for c, _, _ in SKILLS]
    s_idx = {n: i for i, n in enumerate(skills)}
    tracks = [n for n, _ in TRACKS]
    t_idx = {n: i for i, n in enumerate(tracks)}
    c_idx = {n: i for i, n in enumerate(COMPANY_ORDER)}
    l_idx = {n: i for i, n in enumerate(LEVELS)}

    jobs = []
    for r in conn.execute("SELECT * FROM jobs WHERE active=1 ORDER BY COALESCE(posted_at, first_seen) DESC"):
        locs = json.loads(r["locations"] or "[]")
        level = "Eng Manager" if r["track"] == "Eng Manager" else r["level"]
        jobs.append([
            c_idx.get(r["company"], 0), r["title"], r["url"], t_idx.get(r["track"], len(tracks) - 1),
            l_idx.get(level, len(LEVELS) - 1), " · ".join(locs[:2]) + (f" +{len(locs) - 2}" if len(locs) > 2 else ""),
            r["posted_at"] or "", r["first_seen"], r["min_yoe"],
            [s_idx[s] for s in json.loads(r["skills"] or "[]") if s in s_idx],
            1 if r["description"] else 0,
        ])

    last_run = conn.execute("SELECT MAX(run_at) FROM runs").fetchone()[0]
    runs = {r["company"]: dict(r) for r in conn.execute("SELECT * FROM runs WHERE run_at=?", (last_run,))}
    dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM snapshots ORDER BY date")]
    d_idx = {d: i for i, d in enumerate(dates)}
    snaps = [
        [d_idx[r["date"]], c_idx.get(r["company"], 0), t_idx.get(r["track"], 0),
         -1 if r["skill"] == "__total__" else s_idx.get(r["skill"], -2), r["count"]]
        for r in conn.execute("SELECT * FROM snapshots")
    ]
    snaps = [s for s in snaps if s[3] != -2]
    conn.close()

    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "companies": COMPANY_ORDER, "tracks": tracks, "levels": LEVELS,
        "skills": skills, "skillCats": cats, "jobs": jobs,
        "runs": [runs.get(c) for c in COMPANY_ORDER], "dates": dates, "snaps": snaps,
    }
    site = Path(site_dir)
    vid = data["generated"][:10]
    vdir = site / "reports" / vid
    vdir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    (vdir / "data.json.gz").write_bytes(gzip.compress(payload, 9, mtime=0))

    idx_path = site / "reports" / "index.json"
    versions = json.loads(idx_path.read_text()) if idx_path.exists() else []
    versions = [v for v in versions if v["id"] != vid]
    versions.append({"id": vid, "generated": data["generated"], "jobs": len(jobs)})
    versions.sort(key=lambda v: v["id"], reverse=True)
    idx_path.write_text(json.dumps(versions, ensure_ascii=False, indent=1))

    (site / "index.html").write_text(PAGE_HEAD + (Path(__file__).parent / "template.html").read_text() + "\n</body>\n</html>\n")
    (site / ".nojekyll").touch()
    return vid


PAGE_HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>body{margin:0}[hidden]{display:none!important}</style>
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key         TEXT PRIMARY KEY,
    company     TEXT NOT NULL,
    job_id      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT,
    locations   TEXT,          -- JSON list
    team        TEXT,
    posted_at   TEXT,
    description TEXT,
    track       TEXT,
    level       TEXT,
    min_yoe     INTEGER,
    skills      TEXT,          -- JSON list
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS jobs_company ON jobs(company, active);

CREATE TABLE IF NOT EXISTS runs (
    run_at   TEXT,
    company  TEXT,
    listed   INTEGER,
    targets  INTEGER,
    new      INTEGER,
    closed   INTEGER,
    error    TEXT
);

-- 수집 시점별 스냅샷: 활성 공고 중 스킬 등장 수 (시계열 트렌드용)
CREATE TABLE IF NOT EXISTS snapshots (
    date    TEXT,
    company TEXT,
    track   TEXT,
    skill   TEXT,   -- '__total__' 은 공고 수
    count   INTEGER,
    PRIMARY KEY (date, company, track, skill)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def known_descriptions(conn) -> dict[str, str]:
    return {r["key"]: r["description"] for r in conn.execute("SELECT key, description FROM jobs WHERE description <> ''")}


def upsert(conn, job, meta: dict, today: str) -> bool:
    """신규면 True."""
    row = conn.execute("SELECT key FROM jobs WHERE key=?", (job.key,)).fetchone()
    vals = dict(
        key=job.key, company=job.company, job_id=job.job_id, title=job.title, url=job.url,
        locations=json.dumps(job.locations, ensure_ascii=False), team=job.team, posted_at=job.posted_at,
        description=job.description, track=meta["track"], level=meta["level"], min_yoe=meta["min_yoe"],
        skills=json.dumps(meta["skills"]), today=today,
    )
    if row:
        conn.execute(
            """UPDATE jobs SET title=:title, url=:url, locations=:locations, team=:team,
               posted_at=COALESCE(:posted_at, posted_at), description=:description, track=:track, level=:level,
               min_yoe=:min_yoe, skills=:skills, last_seen=:today, active=1 WHERE key=:key""",
            vals,
        )
        return False
    conn.execute(
        """INSERT INTO jobs VALUES (:key,:company,:job_id,:title,:url,:locations,:team,:posted_at,:description,
           :track,:level,:min_yoe,:skills,:today,:today,1)""",
        vals,
    )
    return True


def close_missing(conn, company: str, seen_keys: set[str], today: str) -> int:
    active = [r["key"] for r in conn.execute("SELECT key FROM jobs WHERE company=? AND active=1", (company,))]
    gone = [k for k in active if k not in seen_keys]
    conn.executemany("UPDATE jobs SET active=0 WHERE key=?", [(k,) for k in gone])
    return len(gone)


def write_snapshot(conn, today: str) -> None:
    conn.execute("DELETE FROM snapshots WHERE date=?", (today,))
    rows = conn.execute("SELECT company, track, skills FROM jobs WHERE active=1").fetchall()
    agg: dict[tuple, int] = {}
    for r in rows:
        for sk in ["__total__"] + json.loads(r["skills"] or "[]"):
            k = (r["company"], r["track"], sk)
            agg[k] = agg.get(k, 0) + 1
    conn.executemany(
        "INSERT INTO snapshots VALUES (?,?,?,?,?)", [(today, c, t, s, n) for (c, t, s), n in agg.items()]
    )

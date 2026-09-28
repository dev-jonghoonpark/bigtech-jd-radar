"""분석 계층: DuckDB가 SQLite 파일을 그대로 붙여서 조회한다 (복사 없음).

- `sql`: 임의 SQL 실행. 테이블은 jobs / runs / snapshots, 그리고 편의 뷰 job_skills.
- `export_parquet`: 수집 회차마다 전체 공고(마감 포함)를 data/parquet/jobs_<date>.parquet 로 남긴다.
  나중에 "그 시점에 열려 있던 공고" 비교를 SQLite 이력 없이도 할 수 있다.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

VIEWS = """
CREATE OR REPLACE VIEW jobs AS SELECT * FROM src.jobs;
CREATE OR REPLACE VIEW runs AS SELECT * FROM src.runs;
CREATE OR REPLACE VIEW snapshots AS SELECT * FROM src.snapshots;
-- 공고 × 스킬 (한 줄에 하나)
CREATE OR REPLACE VIEW job_skills AS
  SELECT key, company, track, level, posted_at, first_seen, active,
         unnest(from_json(skills, '["VARCHAR"]')) AS skill
  FROM src.jobs;
"""


def connect(db_path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute(f"ATTACH '{db_path}' AS src (TYPE sqlite, READ_ONLY)")
    con.execute(VIEWS)
    return con


def sql(db_path: str, query: str) -> None:
    con = connect(db_path)
    con.sql(query).show(max_rows=200, max_width=200)


def export_parquet(db_path: str, out_dir: str = "data/parquet") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / f"jobs_{date.today().isoformat()}.parquet"
    con = connect(db_path)
    con.execute(
        f"COPY (SELECT * EXCLUDE (description), length(description) AS desc_len FROM jobs) "
        f"TO '{out}' (FORMAT parquet, COMPRESSION zstd)"
    )
    return out

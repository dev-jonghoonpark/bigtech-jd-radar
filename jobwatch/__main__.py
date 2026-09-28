"""사용법:
  uv run python -m jobwatch collect [--only Google Meta] [--max-details N]
  uv run python -m jobwatch report
  uv run python -m jobwatch reannotate
  uv run python -m jobwatch sql "SELECT skill, count(*) FROM job_skills WHERE active=1 GROUP BY 1 ORDER BY 2 DESC LIMIT 20"
"""
import argparse
import logging
import sys
from pathlib import Path

from .collect import collect, reannotate

DB = "data/jobs.db"
FAILURES = "data/last_failures.md"


def main():
    ap = argparse.ArgumentParser(prog="jobwatch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", nargs="*")
    c.add_argument("--max-details", type=int)
    sub.add_parser("report")
    sub.add_parser("reannotate")
    q = sub.add_parser("sql")
    q.add_argument("query")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if a.cmd == "sql":
        from .analytics import sql

        return sql(DB, a.query)
    problems = []
    if a.cmd == "collect":
        problems = collect(DB, a.only, a.max_details)
        from .analytics import export_parquet

        export_parquet(DB)
    elif a.cmd == "reannotate":
        reannotate(DB)
    if a.cmd in ("collect", "report", "reannotate"):
        from .report import build
        build(DB, "site")
    if a.cmd == "collect":
        # publish.sh가 이 파일을 보고 알림(GitHub 이슈)을 만든다
        Path(FAILURES).write_text("".join(f"- {p}\n" for p in problems))
        print("\n=== 수집 결과: " + ("정상" if not problems else f"문제 {len(problems)}건"))
        for p in problems:
            print(f"  ! {p}")
        if problems:
            sys.exit(2)


main()

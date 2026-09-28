"""사용법:
  uv run python -m jobwatch collect [--only Google Meta] [--max-details N]
  uv run python -m jobwatch report
  uv run python -m jobwatch reannotate
  uv run python -m jobwatch sql "SELECT skill, count(*) FROM job_skills WHERE active=1 GROUP BY 1 ORDER BY 2 DESC LIMIT 20"
"""
import argparse
import logging

from .collect import collect, reannotate

DB = "data/jobs.db"


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
    if a.cmd == "collect":
        collect(DB, a.only, a.max_details)
        from .analytics import export_parquet

        export_parquet(DB)
    elif a.cmd == "reannotate":
        reannotate(DB)
    if a.cmd in ("collect", "report", "reannotate"):
        from .report import build
        build(DB, "site")


main()

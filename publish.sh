#!/usr/bin/env bash
# 수집 → 리포트 새 버전 생성 → GitHub Pages(gh-pages 브랜치) 배포.
#   ./publish.sh              전체 수집 후 배포 (cron이 매일 실행)
#   ./publish.sh --no-collect 수집 없이 현재 DB로 리포트만 다시 만들어 배포
# 리포트는 site/reports/<날짜>/ 에 버전별로 쌓이고, 같은 날 재실행하면 그 날 버전을 덮어쓴다.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
mkdir -p data/logs
LOG="data/logs/$(date +%F).log"
exec > >(tee -a "$LOG") 2>&1
echo "=== $(date '+%F %T') publish start"

# site/ 는 gh-pages 브랜치의 worktree. 없으면 원격에서 받아 붙인다.
if [ ! -e site/.git ]; then
  git fetch -q origin gh-pages
  git worktree add -q site gh-pages 2>/dev/null || git worktree add -q -B gh-pages site origin/gh-pages
fi
git -C site pull -q --ff-only origin gh-pages || true

if [ "${1:-}" = "--no-collect" ]; then
  uv run python -m jobwatch report
else
  uv run python -m jobwatch collect
fi

cd site
git add -A
if git diff --cached --quiet; then
  echo "변경 없음"
else
  VER=$(python3 -c 'import json;print(json.load(open("reports/index.json"))[0]["id"])')
  git commit -q -m "report: $VER"
  for i in 1 2 3 4; do git push -q origin gh-pages && break; sleep $((2 ** i)); done
  echo "배포: $VER"
fi
find ../data/logs -name '*.log' -mtime +30 -delete
echo "=== $(date '+%F %T') publish done"

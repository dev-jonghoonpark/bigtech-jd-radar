#!/usr/bin/env bash
# 수집 → 리포트 새 버전 생성 → GitHub Pages(gh-pages 브랜치) 배포.
#   ./publish.sh              전체 수집 후 배포 (cron이 매일 실행)
#   ./publish.sh --no-collect 수집 없이 현재 DB로 리포트만 다시 만들어 배포
# 리포트는 site/reports/<날짜>/ 에 버전별로 쌓이고, 같은 날 재실행하면 그 날 버전을 덮어쓴다.
# 수집 중 실패한 회사/공고가 있으면 터미널에 출력하고, 레포에 GitHub 이슈를 열어 알린다(종료 코드 2).
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

notify() {  # $1: 제목, $2: 본문 파일
  gh issue create --title "$1" --body-file "$2" >/dev/null \
    && echo "알림: GitHub 이슈 생성 — $1" || echo "알림 이슈 생성 실패"
}

rc=0
if [ "${1:-}" = "--no-collect" ]; then
  uv run python -m jobwatch report
else
  uv run python -m jobwatch collect || rc=$?
fi
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then  # 2 = 일부 실패(리포트는 생성됨), 그 외 = 전체 실패
  printf '수집 스크립트가 비정상 종료했습니다 (exit %s). 로그: `%s`\n\n```\n%s\n```\n' "$rc" "$LOG" "$(tail -30 "$LOG")" > data/last_failures.md
  notify "수집 실패 $(date +%F): 스크립트 오류" data/last_failures.md
  exit "$rc"
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
cd ..
if [ "$rc" -eq 2 ]; then
  { echo "$(date '+%F %T') 수집에서 문제가 있었습니다. 리포트는 나머지 데이터로 배포했습니다."; echo; cat data/last_failures.md; echo; echo "로그: \`$LOG\`"; } > data/last_issue.md
  notify "수집 실패 $(date +%F): $(grep -c '^- ' data/last_failures.md)건" data/last_issue.md
fi
find data/logs -name '*.log' -mtime +30 -delete
echo "=== $(date '+%F %T') publish done"
exit "$rc"

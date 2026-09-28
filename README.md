# Big Tech JD Radar

MANGOS(Meta, Anthropic, Nvidia, Google, OpenAI, SpaceX) + FAANG(Apple, Amazon, Netflix) + Oracle, Microsoft의
Software Engineer / ML 채용공고를 모아, JD에서 기술 키워드를 뽑고 트렌드를 보는 도구.

대시보드: https://dev-jonghoonpark.github.io/bigtech-jd-radar/ (상단 “버전”에서 이전 리포트 보기)

## 배포

```bash
./publish.sh               # 수집 → 새 버전 리포트 생성 → gh-pages 푸시 (cron: 매일 07:00 KST)
./publish.sh --no-collect  # 수집 없이 현재 DB로 리포트만 다시 배포
```

- `site/`는 `gh-pages` 브랜치의 git worktree. 리포트는 `site/reports/<날짜>/data.json.gz`로 쌓이고
  `reports/index.json`이 버전 목록이다. 같은 날 재실행하면 그 날 버전을 덮어쓴다. 버전당 약 400KB(gzip).
- 수집 중 문제가 있으면(회사 수집 실패, 공고 수 급감, JD 상세 실패) 터미널에 출력하고
  이 레포에 **GitHub 이슈**를 연다. 종료 코드 2 = 일부 실패(리포트는 배포됨), 그 외 비 0 = 전체 실패(배포 안 함).
- 로그: `data/logs/<날짜>.log` (30일 보관)

## 개별 명령

```bash
uv run python -m jobwatch collect            # 전체 수집 → data/jobs.db, site/ 리포트 갱신
uv run python -m jobwatch collect --only Meta Google
uv run python -m jobwatch report             # DB에서 대시보드만 다시 생성
uv run python -m jobwatch reannotate         # 분류 규칙/스킬 사전 수정 후 저장된 JD에 재적용
```

로컬에서 보기: `cd site && python3 -m http.server` → http://localhost:8000

## 구조

| 파일 | 역할 |
|---|---|
| `jobwatch/sources.py` | 회사별 수집기. 공식 채용 사이트의 공개 JSON 엔드포인트 사용 |
| `jobwatch/classify.py` | 대상 직무 필터(제목 기준), 직무 트랙·레벨 분류, 요구 경력 추출 |
| `jobwatch/skills.py` | 기술 키워드 사전 (카테고리 → 정규식). 여기에 추가하면 됨 |
| `jobwatch/analytics.py` | DuckDB로 SQLite를 붙여 분석 (`python -m jobwatch sql "..."`), 수집마다 Parquet 스냅샷 |
| `jobwatch/db.py` | SQLite: `jobs`(공고), `runs`(수집 이력), `snapshots`(회차별 스킬 등장 수) |
| `jobwatch/report.py`, `template.html` | 대시보드 생성 |

| 회사 | 출처 |
|---|---|
| Anthropic, SpaceX | Greenhouse API |
| OpenAI | Ashby API |
| Nvidia | Workday CXS API (직군 패싯별로 분할 — 검색 상한 2000건) |
| Google | careers 검색 페이지에 내장된 데이터 |
| Apple | jobs.apple.com 검색/상세 페이지의 hydration 데이터 (Software & Services, ML & AI 서브팀) |
| Amazon | amazon.jobs search.json (software-development, machine-learning-science, research-science, data-science) |
| Netflix | Eightfold API |
| Microsoft | Eightfold PCSX API (키워드 여러 개로 검색 후 합침) |
| Oracle | Oracle HCM Cloud REST |
| Meta | metacareers.com이 일반 요청을 막아서 헤드리스 Chromium으로 GraphQL 응답을 가로챔 |

## 동작 방식

- JD 상세는 **처음 보는 공고만** 가져온다. 두 번째 수집부터는 목록만 받으므로 빠르다.
- 목록에서 사라진 공고는 `active=0`(마감)으로 표시. 단, 목록이 직전 활성 공고 수의 50% 미만이면
  사이트 장애로 보고 마감 처리를 건너뛴다.
- 매 수집마다 `snapshots`에 스킬 등장 수를 기록해 회차별 추이를 그린다.
- Meta는 `JOBWATCH_CHROME` 환경변수로 Chromium 경로를 바꿀 수 있다.

## 한계

- 직무 필터/트랙 분류는 제목 정규식 기반이라 경계 사례는 틀릴 수 있다 → `classify.py` 수정 후 `reannotate`.
- 사이트 구조가 바뀌면 해당 회사 수집기가 실패한다. 대시보드 하단 “마지막 수집 상태”에서 확인.

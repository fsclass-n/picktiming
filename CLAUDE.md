# CLAUDE.md — 타임픽(TimePick) 운영 매뉴얼

Claude는 이 저장소에서 작업을 시작하기 전에 이 문서를 먼저 읽는다.
이 문서의 규칙이 `.claude/rules/ecc/`(ECC 공통 규칙)와 충돌하면 **이 문서를 우선**한다.

## 1. 프로젝트 한 줄 요약

RPA가 실제 제품(`rpa/catalog.json`)의 다나와·에누리 가격을 하루 4회 수집(GitHub Actions) → FastAPI 백엔드가 저장·분석(scikit-learn) → Gemini가 "지금 사도 되는가"를 설명 → 정적 프런트엔드가 보여준다.
Final-Project 3조 팀 저장소이며 `main`에 push하면 **실제 운영 환경(Netlify · Render · AWS EC2)에 자동 배포**된다.

운영 구성: **Netlify = 프런트엔드 데모 모드(API 연결 없음)**, **Render = Static Site(`timepick`) + API Web Service(`timepick`, 기존 주소) 분리**,
**EC2 = nginx 같은 도메인 풀스택**(Render와 EC2는 서로 호출하지 않음),
**DB = TiDB 하나를 로컬·Render·EC2가 공유**(MySQL 8은 CI 호환성 테스트 전용), **설정 = `.env` 하나**(로컬 작성 → EC2 `scp` → Render "Add from .env").
Render 배포는 Auto-Deploy "After CI Checks Pass", EC2 배포는 `deploy.yml`. 실제 가격 수집은 GitHub Actions(`collect-render.yml`) 한 곳에서만 하고, EC2 rpa 컨테이너는 `COLLECT_ENABLED=false`로 재학습·리포트만 한다.

## 2. 폴더와 배포 대상

| 경로 | 내용 | 배포 대상 (main push 시) |
|---|---|---|
| `frontend/` | React 19 · Vite 8 · Tailwind CSS v4, `src/App.jsx` 중심 고객 UI | Netlify, Render(Static Site, `VITE_API_URL`), EC2(nginx 이미지) |
| `netlify.toml` | Netlify 설정 (base=frontend) | Netlify |
| `backend/` | Python 3.11 · FastAPI · SQLAlchemy, `backend/Dockerfile`(Render 백엔드·EC2·CI 공용 API 이미지) | Render(Web Service), EC2(api) |
| `render.yaml`, `.dockerignore`(루트) | Render Blueprint(Static Site + Web Service), Docker 빌드 컨텍스트(저장소 루트) 필터 | Render |
| `rpa/` | 가격 수집기(Requests · BeautifulSoup), Docker | EC2(rpa) |
| `docker-compose.yml` | EC2 전체 스택(web + api + rpa, DB는 TiDB) | EC2 전체 재빌드 |
| `deploy/` | nginx.conf, EC2 설정 스크립트 | EC2(nginx 재시작) |
| `.github/` | CI(`ci.yml`), 배포(`deploy.yml`, `scripts/detect-changes.sh`), Render 수집(`collect-render.yml`) | 배포 없음(파이프라인 자체 변경) |
| `.claude/`, `CLAUDE.md`, `README.md`, `docs/` | Claude 설정·문서 (배포 절차는 `docs/md/README.md`) | **배포 없음** |

## 3. 자주 쓰는 명령

```bash
# 설치 (저장소 루트, .venv 활성화 후)
pip install -r requirements.txt

# 테스트·린트 — 작업 완료 전에 바뀐 영역은 반드시 실행
ruff check backend rpa
cd backend && pytest -q        # 임시 SQLite (.env의 TiDB를 쓰지 않음)
cd rpa && pytest -q
cd frontend && npm ci && npm run build

# 화면만 개발 (백엔드·DB 없이 데모; PowerShell: $env:VITE_DEMO="1"; npm run dev)
cd frontend && VITE_DEMO=1 npm run dev
# 실제 API 연동: 다른 터미널에서 FastAPI 실행 후 frontend에서 npm run dev
# 브라우저 회귀 검사: npm run build && npm run preview 실행 후 저장소 루트에서
python frontend/tests/ui_smoke.py

# 로컬 실행 — .env가 운영 TiDB를 가리킨다(로컬에서 바꾼 데이터 = 운영 데이터)
cd backend && uvicorn app.main:app --reload                         # http://localhost:8000 (화면 + API)

# 배포 대상 미리보기 (바뀐 파일 → 어떤 배포가 일어나는지)
CHANGED_FILES="backend/app/main.py" EVENT=push bash .github/scripts/detect-changes.sh
```

## 4. 배포 보호 규칙 (반드시 지킨다)

1. **push 금지**: 사용자가 명시적으로 요청하지 않으면 `git push`하지 않는다. 특히 `main` push는 곧 운영 배포다.
   push 전에는 2번 표 기준으로 "어떤 배포가 일어나는지"를 사용자에게 먼저 알린다.
2. **배포 설정 파일은 확인 후 수정**: `netlify.toml`, `render.yaml`, `docker-compose.yml`, `deploy/**`, `.github/**`,
   `backend/Dockerfile`, `rpa/Dockerfile`, `requirements*.txt`, `.dockerignore`는 수정 전에 이유와 영향을 설명하고 승인을 받는다.
3. **헬스 체크 유지**: `GET /health`는 Render·EC2·CI가 모두 사용한다. 경로·응답을 바꾸지 않는다.
4. **비밀값**: `.env`·API 키·DB 접속 문자열을 커밋하거나 출력하지 않는다. 새 환경 변수가 필요하면 `.env.example`과 `render.yaml`(`sync: false`)에 키만 추가하고,
   세 환경(로컬·EC2·Render)에서 같은 값으로 동작하게 만든다(환경별로 달라야 하는 값은 코드 기본값으로 처리).
   Gemini 키는 서버(backend)에만 둔다. 브라우저 코드에서 Gemini를 직접 호출하지 않는다.
5. **`frontend/public/js/config.js`**: Vite가 빌드 결과에 복사한다. 커밋되는 버전은 `API_BASE_URL: ""`(데모 모드)를 유지한다.
   EC2(nginx)·로컬 풀스택(FastAPI)은 `/js/config.js`를 같은 도메인 설정(`"/"`)으로 바꿔 응답한다.
   Render Static Site는 빌드 시 `VITE_API_URL`(백엔드 주소)을 주입하고, 백엔드는 `FRONTEND_URL`로 CORS·소셜 로그인 복귀를 맞춘다.
   두 값은 Render 전용이라 `.env`에 넣지 않는다(docs/md/07-deploy-render.md).
   화면 문구는 `t('한국어 원문')`으로 쓰고 영어는 `src/lib/i18n-en.js`에 넣는다(`npm run i18n:check`). 색은 slate·brand 유틸리티를 써야 다크 테마가 자동 적용된다(docs/md/03-frontend.md 3절).
   Netlify에 `API_BASE_URL`을 등록하지 않는다(데모 모드 유지 결정).
6. **프런트엔드 빌드 체계 유지**: 사용자가 요청한 React(Vite) + Tailwind CSS v4를 사용한다. `npm ci && npm run build`로 검증한다.
   고객 UI와 상호작용은 `frontend/src/App.jsx`, 디자인 토큰은 `src/index.css`에 있다. 관리자 페이지는 필요 시 지연 로드한다.
   가격·추천 점수는 API 응답으로 표시하고, 전체 이력이 확인된 경우에만 역대 최저가로 표시한다.
7. **DB 호환성**: 로컬·Render·EC2 모두 TiDB(MySQL 호환), CI는 SQLite와 MySQL 8 둘 다 테스트한다.
   한쪽 DB에서만 동작하는 SQL·타입(PostgreSQL 전용 문법 등)을 쓰지 않는다.
8. **데이터 삭제 금지**: 로컬도 운영 TiDB를 쓴다. `python -m app.seed --reset`, `TEST_DATABASE_URL=<TiDB>` 테스트는 운영 데이터를 지우므로 실행하지 않는다.
   DB 구조를 바꾸는 실험은 사용자 승인 후 별도 DB(예: `timepick_dev`)에서 한다.
9. **RPA 수집 원칙**: robots.txt 확인, 같은 사이트 요청 간격(기본 3초, robots `Crawl-delay` 우선) 유지, `rpa/malls.json`에 등록된(약관상 허용된) 쇼핑몰만 수집한다.
   차단(403·429·CAPTCHA)을 우회하지 않는다: User-Agent 위장·IP 교체·CAPTCHA 풀이 금지. 수집 위치는 GitHub Actions 한 곳(이중 접속 금지).
10. **Render 무료 플랜**: 콜드 스타트와 메모리 제한이 있다. 무거운 의존성·상주 작업을 API 컨테이너에 추가하지 않는다.

## 5. 코드 규칙

- Python: `ruff.toml` 기준(line-length 170, py311, isort first-party = `app`, `collector`). 린트 설정을 완화하지 말고 코드를 고친다.
- API는 `/api/v1` 아래에 두고 기존 라우터(`backend/app/routers/`) 구조를 따른다. 응답 형식을 바꾸면 `frontend/src/lib/mock.js`도 같은 형식으로 맞춘다(데모 모드가 깨지지 않게).
- 새 기능·버그 수정에는 pytest 테스트를 추가한다. ECC 규칙의 "커버리지 80%"는 목표치이며, **기존 테스트 전부 통과**가 필수 조건이다.
- 커밋 메시지는 기존 이력처럼 짧은 영어 명령문을 쓴다(예: `Deploy only the targets whose folders changed`).
- 문서·주석은 한국어로 쓴다.

## 6. Claude 설정(`.claude/`) 구성

영상(신영선의 AI탐구, "클로드코드 설치 30분 마스터 강의")에서 소개한 방식대로 ECC와 Anthropic 공식 스킬을 프로젝트에 설치했다.

| 위치 | 역할 (주방 비유) |
|---|---|
| `CLAUDE.md` (이 파일) | 주방 운영 매뉴얼 — 출근하면 가장 먼저 읽는 문서 |
| `.claude/agents/` | 전문 셰프(서브에이전트) — `planner`, `code-reviewer`, `python-reviewer`, `fastapi-reviewer`, `security-reviewer`, `database-reviewer` 등 |
| `.claude/skills/` | 레시피(스킬) — ECC 스킬 + Anthropic 공식 스킬(`frontend-design`, `webapp-testing`, `skill-creator`, `mcp-builder` 등) |
| `.claude/commands/` | 단축 주문(슬래시 명령) — `/plan`, `/code-review`, `/tdd`, `/build-fix` 등 |
| `.claude/rules/ecc/` | 위생 규칙 — `common/`은 항상, 언어별 규칙은 해당 파일을 다룰 때만 로드됨(`paths` 지정) |
| `.claude/settings.json` | 자동 규칙(Hooks, standard 프로필) + 공식 문서 스킬 플러그인(docx·pdf·pptx·xlsx) 등록 |
| `.claude/scripts/` | Hooks가 실행하는 Node.js 스크립트 |

- 출처: ECC v2.2.3 (`affaan-m/ECC`, MIT, `--target claude-project --profile developer --enable-hooks`), `anthropics/skills`의 Apache-2.0 스킬.
- docx·pdf·pptx·xlsx 스킬은 라이선스상 재배포가 금지되어 파일을 복사하지 않고 `settings.json`의 `enabledPlugins`로 등록했다. 처음 실행하면 Claude Code가 설치 여부를 묻는다.
- 이 프로젝트와 관계없는 프레임워크의 스킬은 사용하지 않는다. 프런트엔드는 React·Vite, 백엔드는 FastAPI다.

### Hooks 조절

- 프로필 변경: 환경 변수 `ECC_HOOK_PROFILE=minimal|standard|strict` (기본 standard)
- 특정 훅 끄기: `ECC_DISABLED_HOOKS="pre:edit-write:gateguard-fact-force,stop:desktop-notify"`
- `pre:edit-write:gateguard-fact-force`는 파일을 처음 수정할 때 한 번 막고 "관련 코드를 먼저 확인하라"고 요구한다. 정상 동작이다.
- 개인 설정은 `.claude/settings.local.json`에 둔다(Git 제외).

## 7. 작업 완료 전 체크리스트

- [ ] 바뀐 영역의 `ruff` · `pytest` 통과
- [ ] 2번 표 기준으로 이번 변경이 어떤 배포를 일으키는지 사용자에게 보고
- [ ] 프런트엔드 변경 시 빌드 및 `frontend/tests/ui_smoke.py` 통과
- [ ] `.env`·비밀값·빌드 결과(`frontend/dist/`)가 커밋에 섞이지 않았는지 확인
- [ ] API 응답 형식을 바꿨다면 `frontend/src/lib/mock.js`도 수정

## 8. 실수 기록 (같은 실수를 반복하지 않도록 계속 추가)

- (예시) 날짜 — 무엇을 잘못했고 → 앞으로 어떻게 한다

# 01. 프로젝트 개요와 구조

## 1. 서비스 한 줄 설명

**RPA가 실제 제품 13종의 다나와·에누리 가격을 하루 4회 수집**하고(GitHub Actions, 공공 가격은 설정된 경우 별도 일일 작업),
**학습 모델 또는 규칙이 "과거 흐름상 지금이 싼 시점인가"를 점수로 판정**하며,
**Google Gemini가 그 근거를 자연어로 설명**하는 가격 비교·구매 적기 추천 서비스입니다.
(Final-Project 3조: 박미금(조장·발표자), 김모란, 이오리, 홍기흥)

개정 기준은 `279a4ce`입니다. [현재 상태·발표 자료](README.md)를 함께 확인하세요.
효과·모델 정확도·수집 성공률은 별도 측정 자료 없이 수치로 단정하지 않습니다.

## 2. 기술 스택

| 구분 | 기술 | 위치 |
|---|---|---|
| Frontend | React 19, Vite 8, Tailwind CSS v4, FontAwesome, SVG 가격 차트, 관리자 Plotly | `frontend/` |
| Backend | Python 3.11.9, FastAPI, SQLAlchemy 2, PyMySQL, PyJWT, bcrypt | `backend/` |
| AI / ML | Google Gemini(`gemini-2.5-flash`), scikit-learn RandomForest, pandas, NumPy | `backend/app/ai`, `backend/app/ml` |
| RPA | Requests, BeautifulSoup4, pandas, 내장 스케줄러, JSON-LD 파싱, 선택적 Playwright·S3 | `rpa/` |
| DB | TiDB Cloud(로컬·Render·EC2 공용), SQLite(자동 테스트), MySQL 8(CI 호환성 테스트) | — |
| 배포 | Netlify, Render(Docker), AWS EC2(docker compose + nginx) | `netlify.toml`, `render.yaml`, `docker-compose.yml`, `deploy/` |
| CI/CD | GitHub Actions | `.github/` |

## 3. 폴더 구조

```
picktiming/
├── frontend/                 # Vite가 빌드하는 React SPA
│   ├── src/App.jsx           # 고객 화면·검색·차트·모달·가입 상태
│   ├── src/index.css         # Tailwind v4 테마·반응형·키보드 포커스
│   ├── src/lib/api.js        # REST 클라이언트
│   ├── src/lib/mock.js       # 브라우저 데모 API
│   ├── src/lib/auth.jsx      # 인증 상태
│   ├── src/pages/Admin*      # 지연 로드하는 관리자 화면
│   ├── public/js/config.js   # 커밋되는 값은 데모 모드
│   ├── tests/ui_smoke.py     # 로컬 브라우저 회귀 검사
│   └── dist/                # 빌드 결과(Git 제외)
├── backend/                  # FastAPI (Render · EC2 공용 Docker 이미지)
│   ├── app/main.py           # 앱 생성, CORS, 라우터 등록, /health
│   ├── app/config.py         # 환경 변수 설정
│   ├── app/database.py       # DB 엔진 (SQLite / MySQL·TiDB + TLS)
│   ├── app/models.py         # 테이블 12개
│   ├── app/routers/          # auth, products, ai, user_data, rpa, admin
│   ├── app/services/         # 가격 비교, 적기 판정, 알림
│   ├── app/ml/               # 피처, 학습, 모델 저장(DB)
│   ├── app/ai/gemini.py      # Gemini 프롬프트·검증·템플릿 대체
│   ├── app/jobs/             # 주간 리포트(엑셀)
│   ├── app/seed.py           # 시연 데이터
│   ├── tests/                # pytest
│   └── Dockerfile            # EC2·CI용 API 이미지 (컨텍스트 = 저장소 루트)
├── rpa/                      # 가격 수집기 (EC2 컨테이너)
│   ├── collector/            # http, parsers, jobs, scheduler, api_client
│   ├── malls.json            # 쇼핑몰별 CSS 셀렉터
│   ├── public_price_map.json # 참가격 상품 ID ↔ 모델 번호
│   ├── tests/                # pytest
│   └── Dockerfile
├── deploy/                   # nginx.conf, config.same-origin.js, ec2-setup.sh
├── docker-compose.yml        # EC2: web(nginx) + api + rpa (DB는 TiDB)
├── render.yaml               # Render Blueprint (서비스 이름 picktiming, Dockerfile)
├── Dockerfile                # Render 풀스택: React 빌드 + FastAPI
├── requirements.txt          # Python 통합 의존성
├── .dockerignore             # 이미지에 불필요한 문서·로컬 파일 제외
├── netlify.toml              # Netlify (base=frontend, 데모 모드)
├── .github/                  # ci.yml, deploy.yml, collect-render.yml, scripts/detect-changes.sh
├── .env.example              # 환경 변수 예시 (.env는 Git 제외)
├── .claude/, CLAUDE.md       # Claude Code 설정 (배포와 무관)
└── docs/                     # 이 문서들
```

## 4. 전체 데이터 흐름

```
[KST 00·06·12·18시] 수집기 — GitHub Actions 한 곳에서만 실행 (EC2 rpa는 COLLECT_ENABLED=false)
   GitHub Actions(07분) ──▶ https://timepick-api.onrender.com (Render API)
   │ 0) PUT  /api/v1/rpa/catalog         rpa/catalog.json의 실제 제품 13종·다나와·에누리 판매처를 DB와 맞춤(시연 쇼핑몰 비활성)
   │ 1) GET  /api/v1/rpa/listings        수집 대상(판매 페이지) 목록
   │ 2) 다나와·에누리 상품 페이지 수집 (robots.txt 확인, 같은 사이트 3초 간격, JSON-LD 최저가)
   │ 3) pandas 정제 (중복·이상치 제거)
   │ 4) POST /api/v1/rpa/prices/bulk     가격 저장(같은 시간대 중복은 건너뜀) → 적기 판정 갱신 → 알림 생성
   ▼
TiDB (운영 DB) ◀── Render API, EC2 API 둘 다 같은 DB 사용
   ▲
   │ 사용자 요청 (JWT 로그인 후) — 각 서버의 프런트엔드가 같은 도메인의 API를 호출
Render(timepick-api.onrender.com) / EC2(picktiming.duckdns.org): 검색 / 상세·가격 비교 / 적기 판정 / AI 조언·상담 / 관심 상품 / 알림

Netlify(picktiming.netlify.app): 데모 모드 — 브라우저 목업 데이터만 사용, 서버·DB와 연결 없음
```

| 시각(KST) | 작업 | 결과 |
|---|---|---|
| 00·06·12·18시 | 가격 수집(`collect`, GitHub Actions) | `price_history` 추가, 판정·알림 갱신 |
| 매일 03시 | 모델 재학습(`train`) | 성능이 같거나 좋으면 새 모델을 활성화(`model_versions`) |
| 매일 06시 | 참가격 공공데이터(`public`) | `public_prices` 갱신 (키가 없으면 건너뜀) |
| 매주 월 07시 | 주간 리포트(`report`) | EC2: `~/picktiming/reports/`, Render: Actions 아티팩트(30일 보관) |

## 5. 환경별 차이 한눈에 보기

| 항목 | 로컬 PC | Netlify | Render | EC2 |
|---|---|---|---|---|
| 주소 | http://localhost:8000 | picktiming.netlify.app | timepick-api.onrender.com | picktiming.duckdns.org |
| DB | **TiDB** | 없음 | **TiDB** | **TiDB** (세 곳 같은 DB) |
| 프런트엔드 제공 | FastAPI(StaticFiles, 저장소 `frontend/` 자동) | Netlify CDN | FastAPI(StaticFiles) | nginx |
| API 주소(프런트) | 같은 도메인(`/`) | 없음(데모 모드) | 같은 도메인(`/`) | 같은 도메인(`/`) |
| 실행 방식 | `uvicorn` | 정적 호스팅 | `Dockerfile(저장소 루트)` (컨텍스트: 저장소 루트) | `backend/Dockerfile`, `rpa/Dockerfile` (compose) |
| RPA | 수동 실행 | 없음 | GitHub Actions 예약 실행 | 컨테이너 상주 |
| 설정 값 | 루트 `.env` | 없음 | **같은 `.env`** 를 Environment에 붙여 넣기 | **같은 `.env`** 를 `~/picktiming/.env`로 복사 |
| 배포 | — | Netlify Git 연동 | 커밋 → CI 통과 → Render Auto-Deploy | 커밋 → CI 통과 → GitHub Actions SSH |

다음 문서: [02. 백엔드](02-backend.md)

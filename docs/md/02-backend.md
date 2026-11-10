# 02. 백엔드 (FastAPI)

소스: [`backend/app/`](../../backend/app). 같은 코드를 두 가지 이미지로 빌드합니다.

| 이미지 | Dockerfile | 빌드 컨텍스트 | 내용 | 사용처 |
|---|---|---|---|---|
| API | [`backend/Dockerfile`](../../backend/Dockerfile) | 저장소 루트 `.` | API만 (화면은 Render Static Site 또는 EC2 nginx가 담당) | **Render 백엔드**, EC2, CI |
| 통합(전환·롤백용) | [`Dockerfile(저장소 루트)`](../../Dockerfile) | 저장소 루트 `.` | API + React 빌드 결과 (`FRONTEND_DIR=/app/frontend`) | Render 되돌릴 때만 |

Render는 화면(Static Site)과 API(Web Service)를 분리해 배포합니다(07 문서). 백엔드는 `backend/Dockerfile`을 사용합니다.
Python 의존성은 루트 [`requirements.txt`](../../requirements.txt) 하나로 관리합니다.

## 1. 시작 과정

[`main.py`](../../backend/app/main.py) 기준:

1. 환경 변수 읽기 → `APP_ENV=production`인데 `JWT_SECRET`·`RPA_API_KEY`가 비어 있거나 기본값이면 **기동 거부**
2. `init_db()` → 테이블이 없으면 생성 (`create_all`, 별도 마이그레이션 도구 없음)
3. CORS 설정(`ALLOWED_ORIGINS` + `FRONTEND_URL` 출처 자동 추가, 메서드 `GET POST PATCH DELETE OPTIONS`·헤더 `Authorization`, `Content-Type`만 허용, 쿠키 미사용), 라우터 6개를 `/api/v1` 아래에 등록
4. `GET /health` → DB에 `SELECT 1`을 실행하고 `status`, `env`, `gemini`를 응답합니다. `gemini`는 키 설정 여부이며 실제 생성 성공을 의미하지 않습니다.
5. 화면 제공 방식(`create_app`)은 환경에 따라 하나만 선택됩니다.
   - **화면 폴더 있음**(로컬 `frontend/dist`, 통합 이미지): 아래처럼 같은 도메인에서 화면 제공
   - **`FRONTEND_URL` 있음**(Render 백엔드): API 전용. `/api/*`·`/docs`·`/health` 외의 GET 화면 경로를 Static Site의 같은 경로로 302 이동, 소셜 로그인도 이 주소로 복귀
   - **둘 다 없음**(EC2 api 컨테이너): `/`에서 API 안내 JSON만 응답(화면은 nginx)

   화면 폴더는 `FRONTEND_DIR`, 비어 있으면 저장소의 `frontend/dist/`(로컬 빌드 결과)를 찾습니다.
   API 경로(`/api/v1`, `/health`, `/docs`, `/openapi.json`)가 먼저 처리되고 나머지는 정적 파일입니다.
   - `/js/config.js` → `API_BASE_URL: "/"`(같은 도메인)를 동적으로 응답 (저장소의 데모용 config.js 대신)
   - React 경로는 SPA `index.html`로 연결하고, 없는 정적 파일은 404 처리합니다.
   - 보안 헤더(`X-Frame-Options`, `nosniff`, `Referrer-Policy`)를 추가합니다.
   - 폴더가 없으면(EC2 api 컨테이너 — 화면은 nginx 담당) `/`는 API 안내 JSON을 돌려줍니다.
6. DB 접속: `DB_SSL_CA`에 값이 있으면 TLS(인증서·호스트 이름 검증). 그 경로의 파일이 없으면(Windows 로컬) certifi 인증서를 사용하므로
   같은 `.env`를 로컬·EC2·Render에서 그대로 쓸 수 있습니다([`database.py`](../../backend/app/database.py)).

Docker 실행 명령은 `uvicorn app.main:app --port ${PORT:-8000}` 입니다. Render는 `PORT`를 주입하고(기본 10000), EC2는 8000을 씁니다.

## 2. 환경 변수

[`config.py`](../../backend/app/config.py), [`.env.example`](../../.env.example) 기준입니다.
**`.env` 하나를 로컬·EC2·Render에서 같은 값으로** 씁니다(Render는 Environment → "Add from .env"로 붙여 넣기).

| 변수 | 코드 기본값 | `.env` 값 (세 환경 공용) | 설명 |
|---|---|---|---|
| `APP_ENV` | development | `production` | `production`이면 `JWT_SECRET`·`RPA_API_KEY`가 비어 있을 때 기동 거부 |
| `DATABASE_URL` | sqlite:///./picktiming.db | TiDB 접속 문자열 | DB (로컬 포함 모두 TiDB) |
| `DB_SSL_CA` | (없음) | `/etc/ssl/certs/ca-certificates.crt` | 값이 있으면 TLS. 파일이 없는 Windows 로컬은 certifi 사용 |
| `JWT_SECRET` | change-me | 생성한 무작위 값 | 로그인 토큰 서명 키 |
| `RPA_API_KEY` | change-me-rpa | 생성한 무작위 값 | RPA 전용 API 인증 키. GitHub Secret `RENDER_RPA_API_KEY`에도 같은 값 |
| `ALLOWED_ORIGINS` | * | `https://timepick.onrender.com,https://timepick-ai.onrender.com,http://picktiming.duckdns.org,http://localhost:8000,http://localhost:5173` | CORS 허용 출처. 세 환경 공용 값 |
| `FRONTEND_URL` | (없음) | **Render 백엔드에만** `https://timepick.onrender.com` | 분리 배포 화면 주소. CORS 자동 허용·소셜 로그인 복귀·화면 경로 리다이렉트. `.env`·EC2에는 넣지 않음 |
| `ADMIN_EMAILS` | (없음) | 선택 | 이 이메일로 가입하면 관리자 |
| `GEMINI_API_KEY` | (없음) | 선택 | 비우면 규칙 기반 템플릿 문장으로 동작 |
| `GEMINI_MODEL`, `AI_DAILY_LIMIT`, `JWT_EXPIRE_MINUTES`, `TZ` | gemini-2.5-flash, 20, 60, Asia/Seoul | 넣지 않음 | 기본값 사용 |
| `FRONTEND_DIR` | (없음 → 저장소 `frontend/` 자동 탐색) | **넣지 않음** | 통합 이미지(루트 `Dockerfile`)만 `/app/frontend`로 설정. Render 백엔드(`backend/Dockerfile`)에는 화면 폴더가 없음 |

## 3. DB 테이블 12개

[`models.py`](../../backend/app/models.py). 시간은 모두 **KST 기준 naive datetime**으로 저장합니다.

| 테이블 | 내용 | 주요 관계 |
|---|---|---|
| `users` | 회원(이메일, bcrypt 해시, 역할 USER/ADMIN) | |
| `products` | 상품(이름, 브랜드, 모델 번호, 카테고리) | |
| `malls` | 쇼핑몰(이름, 주소, robots 확인일, 활성 여부) | |
| `product_listings` | 상품 × 쇼핑몰 판매 페이지 URL | products, malls (상품·쇼핑몰 쌍 유일) |
| `price_history` | 수집 가격(가격, 배송비, 실구매가, 재고, 수집 시각) | product_listings |
| `public_prices` | 참가격 공공 가격 | products |
| `watchlist` | 관심 상품 + 목표가 | users, products |
| `alerts` | 알림(목표가 도달 / 판정 변경) | users, products |
| `timing_predictions` | 적기 판정 결과(점수, 라벨, 90일 최저가 등) 캐시 | products, model_versions |
| `ai_advice_logs` | Gemini 호출 로그·캐시(토큰, 지연, 검증 결과) | products, users |
| `model_versions` | 학습된 모델(joblib 압축 바이너리, F1, 활성 여부) | |
| `rpa_job_logs` | RPA 작업 로그 | |

- 모델 파일은 DB(`model_versions.artifact`, MySQL에서는 LONGBLOB)에 저장됩니다. 시드 데이터 기준 약 **0.24 MiB**(직접 측정)이고,
  트리 깊이가 8로 제한되어 있어 TiDB의 한 행 최대 크기(기본 6 MiB)보다 충분히 작습니다.

## 4. API 목록 (`/api/v1`, 문서: `/docs`)

| 분류 | 메서드·경로 | 인증 | 설명 |
|---|---|---|---|
| 인증 | `POST /auth/signup`, `POST /auth/login`, `GET /users/me` | 로그인 후 `/users/me` | JWT 발급 |
| 상품 | `GET /products/search?q=` | 사용자 | 이름·브랜드·카테고리·모델 번호 검색 (최대 50개) |
| | `POST /products` | 사용자 | 등록된 쇼핑몰 URL만 상품 등록 → 다음 수집부터 반영 |
| | `GET /products/{id}`, `/compare`, `/prices?days=` | 사용자 | 상세, 쇼핑몰별 비교, 가격 차트 |
| AI | `GET /products/{id}/timing` | 사용자 | 적기 점수·라벨(BUY_NOW / WAIT_A_BIT / WAIT / HOLD) |
| | `POST /products/{id}/advice` | 사용자 | Gemini 조언 (24시간 캐시) |
| | `POST /ai/chat` | 사용자 | 상품 질문 상담 (일일 한도) |
| 사용자 | `GET·POST /watchlist`, `PATCH·DELETE /watchlist/{id}` | 사용자 | 관심 상품·목표가 |
| | `GET /alerts`, `POST /alerts/read-all` | 사용자 | 알림 |
| | `GET /deals/today` | **공개** | 오늘의 적기 상품·7일 하락 상품 (홈 화면, 개인 정보 없음) |
| RPA | `GET /rpa/listings`, `POST /rpa/prices/bulk`, `PUT /rpa/public-prices`, `POST /rpa/models`, `POST /rpa/logs`, `POST /rpa/train`, `GET /rpa/reports/weekly` | `X-RPA-KEY` 헤더 | 수집기 전용. `prices/bulk`는 같은 판매처에 같은 시간대(정시~59분) 가격이 이미 있으면 건너뛰고 `duplicate`로 셈 — EC2·Actions 두 수집기가 같은 TiDB에 보내도 중복 저장 안 됨 |
| 관리자 | `GET /admin/rpa-logs`, `GET /admin/ai-metrics` | ADMIN | 수집 현황, AI 사용 지표 |

오류 응답은 모두 `{"code": "...", "message": "..."}` 형식입니다([`errors.py`](../../backend/app/errors.py)).

## 5. 적기 판정과 AI

- **판정**([`services/timing.py`](../../backend/app/services/timing.py)): 쇼핑몰별 일별 최저 실구매가 → 90일 가격 위치, 30일 추세, 할인 주기 등 피처 8종 → RandomForest의 "7일 안에 5% 이상 하락할 확률" → 0~100점과 라벨. 결과는 2시간 동안 `timing_predictions`에 캐시됩니다.
- **학습**([`ml/train.py`](../../backend/app/ml/train.py)): TimeSeriesSplit 5분할로 F1을 계산해 기존 모델보다 같거나 좋을 때만 교체. 데이터가 100행 미만이면 건너뜁니다.
- **Gemini**([`ai/gemini.py`](../../backend/app/ai/gemini.py)): 분석 수치를 문자열로 넘기고, 응답 속 숫자가 입력에 없으면 1회 재요청, 그래도 실패하거나 키가 없으면 템플릿 문장으로 대체합니다. 키는 서버에만 있고 브라우저는 Gemini를 직접 호출하지 않습니다.

## 6. 시드 데이터 (`python -m app.seed`)

[`seed.py`](../../backend/app/seed.py): 시연 쇼핑몰 3곳(`*.example.com`), 상품 12종, 가격 이력 120일, 데모 계정 2개, 초기 모델 학습.

- 데이터가 이미 있으면 아무것도 하지 않습니다(운영 DB에 다시 실행해도 안전).
- 계정: `demo@picktiming.demo`, `admin@picktiming.demo` — 비밀번호는 `SEED_DEMO_PASSWORD` / `SEED_ADMIN_PASSWORD`, 없으면 무작위 생성 후 화면에 출력.
- `--reset`은 **모든 테이블을 삭제**합니다. 운영 TiDB에서 절대 사용하지 않습니다.

## 7. 테스트

- `cd backend && pytest -q` → 기준 커밋 `279a4ce`에서 51건 통과. `.env`의 TiDB 값을 쓰지 않고 임시 SQLite로 실행하며, `TEST_DATABASE_URL`을 주면 그 DB로 실행(CI는 MySQL 8).
- 테스트는 시작할 때 `seed(reset=True)`로 **DB를 비웁니다**. `TEST_DATABASE_URL`에 TiDB 운영 주소를 넣지 않습니다.

## 8. 인증·회원 관리와 발표 시 주의

- 가입 비밀번호는 대·소문자·숫자·특수문자를 포함한 8자 이상입니다.
- Google·Naver·Kakao OAuth 연결 코드가 있으며 실제 사용에는 각 키·공개 URL·콜백 등록이 필요합니다.
- `/auth/demo-login`은 `DEMO_LOGIN_ENABLED` 설정에 따라 허용합니다.
- 관리자는 회원 검색·권한 변경 API를 사용합니다. 테스트 관리자·자기 자신·마지막 관리자 권한 변경에는 제한이 있습니다.
- 모델·AI 검증 코드가 있다는 사실과 모델 정확도·환각률의 실측 성과를 구분합니다.
- API 세부 스키마는 `/docs`와 `backend/app/routers/`가 기준입니다.

다음 문서: [03. 프런트엔드](03-frontend.md)

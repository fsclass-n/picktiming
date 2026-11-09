# 07. [배포 2단계] Render — 프런트엔드(Static Site)·백엔드(Web Service) 분리

Render에서 화면과 API를 **서로 다른 서비스**로 배포합니다. 설정 원본은 [`render.yaml`](../../render.yaml)입니다.

| 서비스 | 종류 | 주소 | 담당 |
|---|---|---|---|
| `timepick` | **Static Site** (무료) | https://timepick.onrender.com | React + Vite 빌드 결과(`frontend/dist`) |
| `timepick-api` | **Web Service** (Docker, 무료) | https://timepick-api.onrender.com | FastAPI API, 구매 적기 판정·Gemini 설명, RPA 수집 수신 |

```
브라우저 ──▶ timepick (CDN 정적 파일)
   │           빌드 시 VITE_API_URL=https://timepick-api.onrender.com 주입
   └──────▶ timepick-api /api/v1/*  (CORS: FRONTEND_URL 출처 허용, Authorization 헤더 토큰)
                 └──▶ TiDB Cloud — 데이터베이스 이름 timepick (2026-11-09 picktiming에서 변경)
GitHub Actions collect-render ──▶ timepick-api /api/v1/rpa/* (X-RPA-KEY, Variable RENDER_URL)
```

- `DATABASE_URL`의 경로는 실제 DB 이름 **`/timepick`** 이어야 합니다. 다르면 `Unknown database`(1049)로 서버가 시작하지 않습니다(0절).
- 화면 경로(`/product/3` 등)로 백엔드 주소에 들어오면 **같은 경로의 Static Site 주소로 302 이동**합니다. `/api/*`, `/docs`, `/health`는 이동하지 않습니다.
- EC2(nginx 같은 도메인)와 Netlify(데모 모드)는 영향이 없습니다.

## 0. 주소 변경: picktiming → timepick (2026-11)

Render의 `onrender.com` 주소는 **서비스를 만들 때의 이름**으로 정해지고, 나중에 이름을 바꿔도 주소는 바뀌지 않습니다.
그래서 새 주소는 새 서비스로 만들고, 예전 서비스(`picktiming`, `picktiming-web`)는 전환이 끝난 뒤 정리합니다.

| 순서 | 할 일 | 확인 |
|---|---|---|
| 1 | TiDB DB 이름 변경(06 문서 8절) 후 `timepick-api`·로컬 `.env`·EC2 `.env`의 **`DATABASE_URL` 경로를 `/timepick`** 으로 → Save, rebuild, and deploy | `https://timepick-api.onrender.com/health` → `"status":"ok"` |
| 2 | `timepick-api`에 `FRONTEND_URL=https://timepick.onrender.com`, `ALLOWED_ORIGINS`(아래 3-1) | 로그에 `Unknown database` 없음 |
| 3 | `timepick` Static Site: `VITE_API_URL=https://timepick-api.onrender.com` → **Manual Deploy**(빌드 시 들어가는 값), Rewrite `/*` → `/index.html` | 화면 로그인·검색, `/product/1` 새로고침 시 404 아님 |
| 4 | GitHub → Settings → Variables → **`RENDER_URL` = `https://timepick-api.onrender.com`** | Actions → Collect (Render) 수동 실행 성공 |
| 5 | 소셜 로그인 콘솔(Google·Naver·Kakao)에 콜백 추가: `https://timepick-api.onrender.com/api/v1/auth/oauth/<google\|naver\|kakao>/callback` | 소셜 로그인 후 timepick 화면으로 복귀 |
| 6 | UptimeRobot 등 깨우기 주소를 `https://timepick-api.onrender.com/health`로 | — |
| 7 | 예전 `picktiming`(Web Service)은 `FRONTEND_URL=https://timepick.onrender.com`으로 바꿔 예전 링크를 새 화면으로 보내거나, 안정 후 **Suspend**. `picktiming-web`은 Suspend | 무료 인스턴스 시간(월 750시간)은 Web Service끼리 나눠 씀 |

### `Unknown database 'timepick'` (1049)

- **원인**: `DATABASE_URL` 경로의 DB 이름이 TiDB에 실제로 있는 DB 이름과 다릅니다. 2026-11-09에는 TiDB에 `picktiming`만 있는데 경로가 `/timepick`이라 발생했고,
  이후 DB 이름을 `timepick`으로 옮겨(06 문서 8절) 해결했습니다. 이제는 반대로 `/picktiming`을 쓰는 곳(예전 서비스·EC2 `.env`)에서 같은 오류가 납니다.
  `.env`에서 `picktiming`을 `timepick`으로 일괄 바꾸면 `ADMIN_EMAILS`, `S3_PREFIX`, `ALLOWED_ORIGINS`의 EC2 주소(`picktiming.duckdns.org`)까지 바뀌니 주의합니다.
- **해결**: TiDB Cloud SQL Editor에서 `SHOW DATABASES;`로 실제 이름을 확인하고 모든 환경의 `DATABASE_URL` 경로를 그 이름으로 맞춥니다.
- 백엔드는 이 오류를 원인과 고칠 값을 담은 한 줄 메시지로 기동 로그에 남깁니다([`database.py`](../../backend/app/database.py)의 `describe_db_error`, 비밀번호는 출력하지 않음).

## 1. 코드에서 바뀐 점

| 위치 | 내용 |
|---|---|
| `frontend/vite.config.js`, `src/lib/api.js` | **`VITE_API_URL`** 을 빌드 시 주입. 끝의 `/`를 정리하고, `https://` 없는 잘못된 값은 빌드를 실패시킴 |
| API 주소 결정 순서 | ① 서버가 응답한 `/js/config.js`(EC2·로컬 풀스택 = `"/"`) → ② `VITE_API_URL`(Render Static Site) → ③ 둘 다 없으면 데모 모드(Netlify) |
| `backend/app/config.py` | **`FRONTEND_URL`** 추가: CORS 허용 목록에 자동 포함, 소셜 로그인 성공·실패 후 이 주소로 복귀 |
| `backend/app/main.py` | CORS 미들웨어를 화면이 쓰는 메서드(`GET POST PATCH DELETE OPTIONS`)·헤더(`Authorization`, `Content-Type`)로 제한, 사전 요청 캐시 10분. `FRONTEND_URL`이 있고 화면 폴더가 없으면 API 전용 + 화면 경로 리다이렉트 |
| `backend/Dockerfile` | Render 백엔드 이미지(API 전용). EC2·CI와 같은 이미지 |
| 루트 `Dockerfile` | **전환·롤백용** 이전 통합 이미지. 분리 배포가 안정되면 삭제 가능 |

## 2. 프런트엔드 — Static Site 만들기

Render 대시보드 → **New → Static Site** → 저장소 `fsclass-n/picktiming`

| 항목 | 값 |
|---|---|
| Name | `timepick` |
| Branch | `main` |
| Root Directory | **`frontend`** |
| Build Command | **`npm install && npm run build`** |
| Publish Directory | **`dist`** (Root Directory 기준 = `frontend/dist`) |
| Auto-Deploy | **After CI Checks Pass** |
| Build Filters → Included Paths | `frontend/**` |

**Environment** (빌드 시 코드에 들어가는 값이라 바꾸면 다시 배포해야 반영됩니다)

| Key | Value |
|---|---|
| `VITE_API_URL` | `https://timepick-api.onrender.com` |
| `NODE_VERSION` | `22` |

위 값으로 **Create Static Site**를 누르면 첫 배포가 시작됩니다. 생성 화면에는 Rewrite·Headers 항목이 **없습니다**.
아래 두 설정은 만들어진 사이트 화면의 **왼쪽 메뉴**에서 추가합니다.

**Redirects/Rewrites** (왼쪽 메뉴 → Redirects/Rewrites → Add Rule) — React Router 화면 경로(`/login`, `/product/3`)를 위해 필수

| Source | Destination | Action |
|---|---|---|
| `/*` | `/index.html` | **Rewrite** |

- 이 규칙이 없으면 홈(`/`)은 열리지만, `/product/3` 같은 주소를 직접 열거나 새로고침하면 **404 Not Found**가 납니다.
- Render는 실제 파일(`/assets/*.js`, `/favicon.svg`)이 있으면 규칙보다 파일을 먼저 응답하므로 JS·CSS는 영향이 없습니다.
- 규칙은 저장 즉시 적용되며 다시 배포할 필요가 없습니다.

**Headers** (왼쪽 메뉴 → Headers → Add Header, 권장)

| Path | Name | Value |
|---|---|---|
| `/*` | `X-Frame-Options` | `DENY` |
| `/*` | `X-Content-Type-Options` | `nosniff` |
| `/*` | `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `/js/config.js` | `Cache-Control` | `no-cache` |
| `/assets/*` | `Cache-Control` | `public, max-age=31536000, immutable` |

> 이름 `timepick`이 이미 쓰이고 있으면 Render가 `timepick-xxxx.onrender.com` 같은 주소를 줍니다.
> **생성 후 실제 주소를 확인**하고, 3단계의 `FRONTEND_URL`·`ALLOWED_ORIGINS`에 그 주소를 넣습니다.

## 3. 백엔드 — Web Service(`timepick-api`) 설정

### 3-1. 환경 변수

**Add from .env**로 비밀값을 넣은 뒤, 아래 값을 확인·추가하고 **Save, rebuild, and deploy**를 누릅니다.

| Key | Value | 역할 |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://<USER>:<PASSWORD>@<HOST>:4000/`**`timepick`**`?charset=utf8mb4` | **DB 이름 timepick** |

| Key | Value | 역할 |
|---|---|---|
| `FRONTEND_URL` | `https://timepick.onrender.com` | CORS 자동 허용, 소셜 로그인 복귀, 화면 경로 리다이렉트 |
| `ALLOWED_ORIGINS` | `https://timepick.onrender.com,https://timepick-api.onrender.com,http://picktiming.duckdns.org,http://localhost:8000,http://localhost:5173` | `.env`와 같은 값(`FRONTEND_URL`은 빠져 있어도 자동 추가) |

`FRONTEND_URL`은 Render 전용 값이라 **`.env`에 넣지 않습니다**(EC2에 들어가면 소셜 로그인이 Render 화면으로 돌아감).
나머지 비밀값(`DATABASE_URL`, `JWT_SECRET`, `RPA_API_KEY`, `GEMINI_API_KEY` …)은 기존처럼 **Add from .env**로 관리합니다.

### 3-2. Static Site 동작 확인

https://timepick.onrender.com 에서 로그인(테스트 계정) → 검색 → 상품 상세가 열리는지 봅니다.
브라우저 개발자 도구 Network에서 API 요청이 `https://timepick-api.onrender.com/api/v1/...`로 가고 CORS 오류가 없어야 합니다.

### 3-3. 서비스 설정 (Settings → Build & Deploy)

| 항목 | 값 |
|---|---|
| Name | `timepick-api` (주소 `https://timepick-api.onrender.com`은 만들 때 이름으로 정해짐) |
| Runtime | Docker, Region Singapore, Instance Free |
| Dockerfile Path | **`./backend/Dockerfile`** (API 전용. 루트 `./Dockerfile`은 화면까지 포함한 예전 통합 이미지) |
| Docker Build Context Directory | `.` (`requirements.txt`가 저장소 루트에 있음) |
| Build Filters → Included Paths | `backend/**`, `requirements.txt`, `render.yaml`, `.dockerignore` |
| Health Check Path | `/health` |
| Auto-Deploy | After CI Checks Pass |

> Blueprint(`render.yaml`)로 서비스를 관리한다면 위 값이 이미 들어 있습니다. Blueprint 동기화 시 Static Site가 함께 만들어지고
> 백엔드도 곧바로 `./backend/Dockerfile`로 바뀌므로, 2단계 화면 확인까지 잠깐 화면이 비는 구간이 생길 수 있습니다.
> 대시보드로 만든 서비스라면 `render.yaml`은 참고용이며, 이 문서 순서대로 직접 바꾸는 편이 중단이 없습니다.

## 4. 확인

| 주소 | 기대 결과 |
|---|---|
| https://timepick.onrender.com/ | 홈 화면, **데모 배너 없음**(실제 API 모드) |
| https://timepick.onrender.com/product/1 | 새로고침해도 404가 아닌 상품 화면(Rewrite 규칙) |
| https://timepick-api.onrender.com/health | `{"status":"ok","env":"production",...}` |
| https://timepick-api.onrender.com/ | **302 →** https://timepick.onrender.com/ |
| https://timepick-api.onrender.com/docs | API 문서(이동 없음) |
| 소셜 로그인 | 제공자 로그인 후 **timepick** 주소의 `/oauth/callback`으로 돌아와 로그인 완료 |

명령으로 CORS를 확인하려면:

```bash
curl -si -X OPTIONS https://timepick-api.onrender.com/api/v1/auth/login \
  -H "Origin: https://timepick.onrender.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" | grep -i access-control-allow-origin
# access-control-allow-origin: https://timepick.onrender.com
```

## 5. 되돌리기

문제가 생기면 백엔드 Settings에서 **Dockerfile Path를 `./Dockerfile`** 로, Build Filter에 `frontend/**`·`Dockerfile`을 다시 넣고 배포합니다.
통합 이미지는 화면 폴더가 있어 `FRONTEND_URL`이 있어도 기존처럼 같은 도메인에서 화면을 제공합니다(소셜 로그인 복귀만 `FRONTEND_URL`을 따르므로 함께 지우세요).

## 6. 자동 배포 — After CI Checks Pass

| 바뀐 경로 | timepick | timepick-api |
|---|---|---|
| `frontend/**` | 배포 | - |
| `backend/**`, `requirements.txt`, `.dockerignore` | - | 배포 |
| `render.yaml` | Blueprint 동기화(관리 중인 경우) | 배포 |
| `docs/`, `rpa/`, `deploy/` | - | - |

- 두 서비스 모두 그 커밋의 **모든** GitHub 검사가 통과해야 배포합니다. EC2 배포 작업이 실패하면 Render도 배포하지 않으니, 원인을 고친 뒤 다시 push하거나 Manual Deploy를 누릅니다.
- 이 방식에서는 GitHub Secret `RENDER_DEPLOY_HOOK_URL`을 **등록하지 않습니다**(중복 배포 방지).
- 배포를 원하지 않는 커밋은 메시지에 `[skip render]`를 넣습니다.

## 7. 무료 플랜 특성

| 특성 | 영향 | 대응 |
|---|---|---|
| Web Service는 15분간 요청이 없으면 잠듦, 깨어나는 데 약 1분 | 화면(Static Site)은 바로 뜨지만 첫 API 응답이 느림 | UptimeRobot 등으로 5분마다 `https://timepick-api.onrender.com/health` 호출 |
| Static Site는 잠들지 않음(CDN) | 화면 로딩은 콜드 스타트 영향 없음 | — |
| 셸·SSH 접속 불가 | Render에서 `python -m app.seed` 실행 불가 | 시드는 로컬 PC에서 TiDB로(06 문서) |
| 상주 작업(Background Worker·Cron) 불가 | 서버 안에서 RPA 스케줄러를 돌릴 수 없음 | GitHub Actions `collect-render.yml`이 매시 수집(10 문서). 깨어날 때까지 `/health`를 기다린 뒤 수집 |
| 메모리 512 MB, 0.1 CPU | 모델 재학습(매일 03시)이 느릴 수 있음 | 백그라운드 실행이라 응답에는 영향 없음 |
| 무료 인스턴스 시간: 워크스페이스 전체 월 750시간 | Web Service 하나를 상시 깨우면 약 744시간 | Static Site는 이 시간에 포함되지 않음 |

기동 실패 시 로그 메시지별 원인은 [11 문서](11-checklist-troubleshooting.md)를 참고합니다.

다음 문서: [08. EC2 배포](08-deploy-ec2.md)

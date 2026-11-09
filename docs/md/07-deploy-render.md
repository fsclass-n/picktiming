# 07. [배포 2단계] Render — 프런트엔드(Static Site)·백엔드(Web Service) 분리

Render에서 화면과 API를 **서로 다른 서비스**로 배포합니다. 설정 원본은 [`render.yaml`](../../render.yaml)입니다.

| 서비스 | 종류 | 주소 | 담당 |
|---|---|---|---|
| `picktiming-web` | **Static Site** (무료) | https://picktiming-web.onrender.com | React + Vite 빌드 결과(`frontend/dist`) |
| `picktiming` | **Web Service** (Docker, 무료) | https://picktiming.onrender.com | FastAPI API, 구매 적기 판정·Gemini 설명, RPA 수집 수신 |

```
브라우저 ──▶ picktiming-web (CDN 정적 파일)
   │           빌드 시 VITE_API_URL=https://picktiming.onrender.com 주입
   └──────▶ picktiming /api/v1/*  (CORS: FRONTEND_URL 출처 허용, Authorization 헤더 토큰)
                 └──▶ TiDB Cloud
GitHub Actions collect-render ──▶ picktiming /api/v1/rpa/* (X-RPA-KEY, 주소 변경 없음)
```

- **기존 주소는 백엔드가 유지**합니다. 수집 워크플로(`RENDER_URL`)와 소셜 로그인 콜백 주소는 바꿀 필요가 없습니다.
- 예전 링크(`https://picktiming.onrender.com/product/3` 등)로 들어오면 백엔드가 **같은 경로의 Static Site 주소로 302 이동**시킵니다. `/api/*`, `/docs`, `/health`는 이동하지 않습니다.
- EC2(nginx 같은 도메인)와 Netlify(데모 모드)는 영향이 없습니다.

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
| Name | `picktiming-web` |
| Branch | `main` |
| Root Directory | **`frontend`** |
| Build Command | **`npm install && npm run build`** |
| Publish Directory | **`dist`** (Root Directory 기준 = `frontend/dist`) |
| Auto-Deploy | **After CI Checks Pass** |
| Build Filters → Included Paths | `frontend/**` |

**Environment** (빌드 시 코드에 들어가는 값이라 바꾸면 다시 배포해야 반영됩니다)

| Key | Value |
|---|---|
| `VITE_API_URL` | `https://picktiming.onrender.com` |
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

> 이름 `picktiming-web`이 이미 쓰이고 있으면 Render가 `picktiming-web-xxxx.onrender.com` 같은 주소를 줍니다.
> **생성 후 실제 주소를 확인**하고, 3단계의 `FRONTEND_URL`·`ALLOWED_ORIGINS`에 그 주소를 넣습니다.

## 3. 백엔드 — 기존 Web Service(`picktiming`)를 API 전용으로 바꾸기

### 3-1. 환경 변수 추가 (먼저)

Environment에 아래 값을 추가하고 **Save, rebuild, and deploy**를 누릅니다. 아직 통합 이미지라 기존 화면은 그대로 동작합니다.

| Key | Value | 역할 |
|---|---|---|
| `FRONTEND_URL` | `https://picktiming-web.onrender.com` | CORS 자동 허용, 소셜 로그인 복귀, 화면 경로 리다이렉트 |
| `ALLOWED_ORIGINS` | `https://picktiming-web.onrender.com,https://picktiming.onrender.com,http://picktiming.duckdns.org,http://localhost:8000,http://localhost:5173` | `.env`와 같은 값(`FRONTEND_URL`은 빠져 있어도 자동 추가) |

`FRONTEND_URL`은 Render 전용 값이라 **`.env`에 넣지 않습니다**(EC2에 들어가면 소셜 로그인이 Render 화면으로 돌아감).
나머지 비밀값(`DATABASE_URL`, `JWT_SECRET`, `RPA_API_KEY`, `GEMINI_API_KEY` …)은 기존처럼 **Add from .env**로 관리합니다.

### 3-2. Static Site 동작 확인

https://picktiming-web.onrender.com 에서 로그인(테스트 계정) → 검색 → 상품 상세가 열리는지 봅니다.
브라우저 개발자 도구 Network에서 API 요청이 `https://picktiming.onrender.com/api/v1/...`로 가고 CORS 오류가 없어야 합니다.

### 3-3. Dockerfile·Build Filter 전환

Settings → Build & Deploy

| 항목 | 이전 | **변경 후** |
|---|---|---|
| Dockerfile Path | `./Dockerfile` | **`./backend/Dockerfile`** |
| Docker Build Context Directory | `.` | `.` (그대로, `requirements.txt`가 저장소 루트에 있음) |
| Build Filters → Included Paths | `backend/**`, `frontend/**`, `Dockerfile`, … | **`backend/**`, `requirements.txt`, `render.yaml`, `.dockerignore`** |
| Health Check Path | `/health` | `/health` (그대로) |
| Auto-Deploy | After CI Checks Pass | 그대로 |

저장 후 **Manual Deploy → Deploy latest commit**. 이제 백엔드는 API만 제공합니다.

> Blueprint(`render.yaml`)로 서비스를 관리한다면 위 값이 이미 들어 있습니다. Blueprint 동기화 시 Static Site가 함께 만들어지고
> 백엔드도 곧바로 `./backend/Dockerfile`로 바뀌므로, 2단계 화면 확인까지 잠깐 화면이 비는 구간이 생길 수 있습니다.
> 대시보드로 만든 서비스라면 `render.yaml`은 참고용이며, 이 문서 순서대로 직접 바꾸는 편이 중단이 없습니다.

## 4. 확인

| 주소 | 기대 결과 |
|---|---|
| https://picktiming-web.onrender.com/ | 홈 화면, **데모 배너 없음**(실제 API 모드) |
| https://picktiming-web.onrender.com/product/1 | 새로고침해도 404가 아닌 상품 화면(Rewrite 규칙) |
| https://picktiming.onrender.com/health | `{"status":"ok","env":"production",...}` |
| https://picktiming.onrender.com/ | **302 →** https://picktiming-web.onrender.com/ |
| https://picktiming.onrender.com/docs | API 문서(이동 없음) |
| 소셜 로그인 | 제공자 로그인 후 **picktiming-web** 주소의 `/oauth/callback`으로 돌아와 로그인 완료 |

명령으로 CORS를 확인하려면:

```bash
curl -si -X OPTIONS https://picktiming.onrender.com/api/v1/auth/login \
  -H "Origin: https://picktiming-web.onrender.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" | grep -i access-control-allow-origin
# access-control-allow-origin: https://picktiming-web.onrender.com
```

## 5. 되돌리기

문제가 생기면 백엔드 Settings에서 **Dockerfile Path를 `./Dockerfile`** 로, Build Filter에 `frontend/**`·`Dockerfile`을 다시 넣고 배포합니다.
통합 이미지는 화면 폴더가 있어 `FRONTEND_URL`이 있어도 기존처럼 같은 도메인에서 화면을 제공합니다(소셜 로그인 복귀만 `FRONTEND_URL`을 따르므로 함께 지우세요).

## 6. 자동 배포 — After CI Checks Pass

| 바뀐 경로 | picktiming-web | picktiming |
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
| Web Service는 15분간 요청이 없으면 잠듦, 깨어나는 데 약 1분 | 화면(Static Site)은 바로 뜨지만 첫 API 응답이 느림 | UptimeRobot 등으로 5분마다 `https://picktiming.onrender.com/health` 호출 |
| Static Site는 잠들지 않음(CDN) | 화면 로딩은 콜드 스타트 영향 없음 | — |
| 셸·SSH 접속 불가 | Render에서 `python -m app.seed` 실행 불가 | 시드는 로컬 PC에서 TiDB로(06 문서) |
| 상주 작업(Background Worker·Cron) 불가 | 서버 안에서 RPA 스케줄러를 돌릴 수 없음 | GitHub Actions `collect-render.yml`이 매시 수집(10 문서). 깨어날 때까지 `/health`를 기다린 뒤 수집 |
| 메모리 512 MB, 0.1 CPU | 모델 재학습(매일 03시)이 느릴 수 있음 | 백그라운드 실행이라 응답에는 영향 없음 |
| 무료 인스턴스 시간: 워크스페이스 전체 월 750시간 | Web Service 하나를 상시 깨우면 약 744시간 | Static Site는 이 시간에 포함되지 않음 |

기동 실패 시 로그 메시지별 원인은 [11 문서](11-checklist-troubleshooting.md)를 참고합니다.

다음 문서: [08. EC2 배포](08-deploy-ec2.md)

# 03. 프런트엔드 — React 가격 탐색 플랫폼

React 19 · Vite 8 · Tailwind CSS v4. 고객 UI와 상호작용은 [`frontend/src/App.jsx`](../../frontend/src/App.jsx)에 모여 있습니다.
API 클라이언트·인증·데모 데이터는 기존 `src/lib/` 모듈을 공유하며, 관리자 페이지 3개는 지연 로드합니다.

최종 발표용 실제 UI 캡처와 데모 구분은 [발표 제작 기준](../발표자료/제작기준.md),
시연 순서는 [7분 시연 시나리오](../발표자료/7분_시연시나리오.md)를 참고합니다.

## 1. 실행

Node.js 22 환경에서:

```powershell
cd frontend
npm ci
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

`http://127.0.0.1:4173`은 운영 DB를 사용하지 않는 데모입니다.

- 화면 개발: `frontend/`에서 `$env:VITE_DEMO="1"; npm run dev`.
- 실제 API 개발: `VITE_DEMO`를 해제하고 FastAPI(8000) + `npm run dev`(5173)를 각각 실행합니다.
- FastAPI가 빌드 화면을 제공하도록 하려면 먼저 `npm run build`를 실행합니다.
- 의존성은 `package-lock.json`으로 고정합니다. 빌드 결과 `dist/`는 커밋하지 않습니다.

## 2. 화면과 상호작용

| 경로 | 기능 | 인증 |
|---|---|---|
| `/` | 공개 홈, 오늘의 적기·7일 가격 변동, 추천 검색·카테고리, 추천 새로고침 | 불필요 |
| `/search` | 검색어·카테고리·적기 필터, 가격·점수 정렬, 관심 카테고리, 상품 URL 등록 | 필요 |
| `/product/:id` | 판매처별 실구매가, 7·30·90일 차트, 적기 신호등, AI 조언, 목표가 모달 | 필요 |
| `/watchlist` | 관심 상품, 목표가 변경, 삭제 확인 | 필요 |
| `/alerts` | 알림 목록, 안 읽은 알림 필터, 모두 읽음 | 필요 |
| `/chat/:id` | 상품별 AI 상담, 추천 질문, 사용량·오류 표시 | 필요 |
| `/login` | 이메일 로그인, 테스트 계정, 설정된 소셜 로그인 | 불필요 |
| `/signup` | 이용 안내 동의 → 계정·관심 카테고리 → 가입·첫 알림 설정 | 불필요 |
| `/oauth/callback` | 서버가 발급한 토큰 확인 후 원래 화면 복귀 | 콜백 |
| `/admin`, `/admin/ai`, `/admin/users` | 수집·모델, AI 사용량, 회원·권한 관리 | ADMIN |
| `/guide`, `/terms`, `/privacy` | 데이터 해석·서비스·개인정보 처리 안내 | 불필요 |

회원가입은 기존 `POST /auth/signup`과 로그인 API를 사용합니다.
가입 성공 후 로그인에 실패하면 새 계정을 중복 생성하지 않고 로그인만 재시도합니다.
필수 동의는 화면 진행 조건이며 서버에 별도의 법적 동의 이력을 저장하는 기능은 추가하지 않았습니다.

관심 카테고리는 `pt_interests_<user_id>`로 **해당 브라우저에만** 저장합니다.
가입 완료 추천과 검색의 ‘내 관심 카테고리’ 필터에 사용하며, 기기 간 동기화는 하지 않습니다.
목표가 알림은 상품별 `POST /watchlist` 또는 `PATCH /watchlist/:id`가 성공한 뒤에만 완료로 표시합니다.
알림 채널은 사이트의 `/alerts`이며 이메일·문자·브라우저 푸시는 제공하지 않습니다.

## 3. 디자인과 데이터 기준

- 제목·가격·지표: **Spoqa Han Sans Neo**, 500 굵기, 자간 -0.02em, 가격은 고정폭 숫자.
  요청서의 `Spoca`는 실제 배포명인 `Spoqa`로 적용했습니다.
- 본문·입력 폼: **Noto Sans KR**. FontAwesome은 기존 npm 패키지를 사용합니다.
- `src/index.css`의 Tailwind `@theme`에 브랜드 보라색과 글꼴을 정의합니다.
  하락·구매 추천은 emerald, 상승·관망은 rose, 본문은 slate를 사용합니다.
- 고정 헤더, 검색 카테고리, 모바일 드로어, 4열 다크 푸터, 스크롤 Top 버튼.
- 모든 공통 버튼은 `inline-flex`, `items-center`, `gap-2`, `whitespace-nowrap`, 최소 높이 44px.
- 상품 이미지는 Unsplash 카테고리 참고 이미지입니다. 실제 모델 사진으로 표시하지 않으며,
  로드 실패 시 대체 아이콘, 이미지 확대 전환, 지연 로딩을 제공합니다.
- 구매 적기 점수는 **0~100점 지표**로 표시합니다. 이를 ‘AI 추천 확률’로 바꾸어 표시하지 않습니다.
- ‘역대 최저가’는 `/prices`의 `all_time_min`과 현재 가격을 비교해 확인된 경우에만 표시합니다.
  역대 범위는 서비스에 수집된 전체 이력이며, 90일 최저가와 구분합니다.
- 가격 차트는 API의 관측값만 사용합니다. 누락값을 가짜 가격으로 채우지 않습니다.
  판매처 선택과 키보드로 조작할 수 있는 날짜 탐색을 제공합니다.
- 카드 차트는 화면 근처에 들어온 상품부터 요청합니다. 비로그인 홈에서는 보호 API를 요청하지 않습니다.
- 고객 가격 차트는 SVG로 렌더링합니다. Plotly는 관리자 통계 화면을 열 때만 로드하며 실패 상태를 표시합니다.

### 3-1. 다크/라이트 테마

- 헤더(모바일은 메뉴 안)의 해·달 버튼으로 즉시 전환하고 `localStorage`의 `tp_theme`에 저장합니다. 저장값이 없으면 기기 설정(`prefers-color-scheme`)을 따릅니다.
- `index.html`의 인라인 스크립트가 첫 화면을 그리기 전에 `<html data-theme>`을 붙여 깜박임을 막습니다([`theme.js`](../../frontend/src/lib/theme.js)).
- [`index.css`](../../frontend/src/index.css) 끝의 다크 블록이 slate 팔레트를 뒤집고(배경은 어둡게, 글자는 밝게) 브랜드·상태 색을 어두운 배경용으로 바꿉니다.
  원래 어두운 영역(푸터·데모 배너·토스트)은 `.keep-dark`로 원래 팔레트를 씁니다. 새 화면도 slate·brand 유틸리티를 쓰면 별도 작업 없이 다크 테마가 적용됩니다.
- 검증: 다크 모드에서 홈·검색·상세·관심·알림·안내 6개 화면의 axe 색 대비 위반 0건.

### 3-2. 한국어/영어

- 헤더의 `EN`/`한국어` 버튼으로 바꾸고 `tp_lang`에 저장한 뒤 화면을 다시 불러옵니다(메뉴·안내처럼 모듈에 정의된 문구까지 같은 언어로 맞추기 위함). 기본값은 한국어입니다.
- 화면 문구는 한국어 원문을 키로 `t('로그인')`처럼 씁니다([`i18n.js`](../../frontend/src/lib/i18n.js)). 영어는 [`i18n-en.js`](../../frontend/src/lib/i18n-en.js)에 있고, 없으면 한국어가 그대로 보입니다.
  변수는 `t('최저 {min}', { min })`, 금액은 `money()`(315,000원 / ₩315,000), 날짜는 `LOCALE`(ko-KR / en-US)로 형식을 맞춥니다.
- 서버·데모 목업의 오류 문구도 같은 사전으로 번역합니다. 상품명·판매처·카테고리 값·AI 답변은 데이터라 번역하지 않습니다(카테고리는 표시할 때만 번역, 검색·필터 값은 한국어 유지).
- 새 문구를 추가하면 `node scripts/i18n-wrap.mjs --report <파일>`로 감쌀 곳을 찾고 사전에 번역을 넣습니다. `npm run i18n:check`(CI 포함)가 누락을 막습니다.

## 4. API 주소와 인증

`index.html`이 `/js/config.js`를 먼저 불러오고, [`src/lib/api.js`](../../frontend/src/lib/api.js)가 아래 순서로 API 주소를 정합니다.

| 순서 | 값 | 동작 | 환경 |
|---|---|---|---|
| ① | `window.APP_CONFIG.API_BASE_URL = "/"` | 같은 도메인의 `/api/v1/…` 호출 | EC2(nginx), 로컬 풀스택(FastAPI), 기본 Vite 개발 서버 |
| ② | 빌드 시 `VITE_API_URL` | 그 주소의 `/api/v1/…` 호출(백엔드 CORS 허용 필요) | **Render Static Site** (`https://timepick-ai.onrender.com`) |
| ③ | 둘 다 없음 | 브라우저의 `src/lib/mock.js`로 응답 | Netlify, preview, `VITE_DEMO=1` |

- `VITE_API_URL`은 [`vite.config.js`](../../frontend/vite.config.js)가 검증합니다. `https://` 없는 값·쿼리·해시가 있으면 **빌드를 실패**시키고, 끝의 `/`는 지웁니다.
  `VITE_DEMO=1`이면 `VITE_API_URL`을 무시합니다. 개발 서버에서 배포된 백엔드를 쓰려면 `VITE_API_URL=https://… npm run dev`.
- 빌드 시 코드에 들어가는 값이므로 Render에서 바꾸면 Static Site를 **다시 배포**해야 반영됩니다.

커밋되는 `public/js/config.js`는 항상 `""`(데모 모드)입니다. EC2는 nginx가 같은 URL에 `"/"`를 응답합니다.
운영 빌드에 DB 접속 주소나 Gemini 키를 넣지 않습니다.

기존 JWT 로그인은 `pt_token`, `pt_user`를 로컬 저장소에 보관하고 Bearer 헤더로 전송합니다.
401 응답 시 로그인 상태를 지웁니다. 권한 검증은 서버에서도 수행합니다.
소셜 로그인 완료 후 URL의 토큰을 지우고, 같은 사이트 경로만 복귀 대상으로 허용합니다.
Render 분리 배포에서는 백엔드가 `FRONTEND_URL`(Static Site)의 `/oauth/callback`으로 돌려보냅니다.

## 5. 접근성·오류 처리

- 네이티브 `dialog`, 모달 내부 Tab 순환, Escape 닫기, 닫은 뒤 원래 버튼으로 포커스 복구.
- 화면 이동 시 본문 포커스, 본문 건너뛰기 링크, 입력 레이블·오류 연결, 상태 메시지.
- 아이콘 외에 텍스트로 구매·대기·하락·상승을 구분합니다.
- `prefers-reduced-motion`에서 모션을 줄이고, 키보드 포커스를 표시합니다.
- 오류·빈 결과·수집 대기·차트 누락을 구분합니다. 이전 검색의 늦은 응답은 무시합니다.
- 모바일 표는 자체 영역 안에서 가로로 스크롤하며 페이지 전체 너비를 늘리지 않습니다.

## 6. 검증

현재 GitHub CI는 React 빌드와 서버·Docker 검증을 실행합니다.
브라우저 검사는 별도로 아래 명령을 실행합니다(로컬 preview를 먼저 켭니다).

```powershell
# 저장소 루트, requirements.txt가 설치된 가상환경
python -m playwright install chromium
python frontend/tests/ui_smoke.py
# Windows에서 이미 설치된 Edge 사용 시:
$env:PLAYWRIGHT_CHANNEL="msedge"
python frontend/tests/ui_smoke.py
```

검사 범위: 검색·정렬·빈 결과, 차트 기간, 목표가 입력/저장, 모달 키보드와 포커스,
가입·첫 알림·관심 카테고리, 로그인 복귀·관리자 권한, AI 조언·상담, 알림 읽음,
375/768/1440px 경로별 가로 넘침, 같은 도메인 API 오류·재시도.
테스트는 `localhost`/`127.0.0.1`만 허용하며 데모 또는 가짜 HTTP 응답을 사용합니다.
운영 API나 TiDB를 대상으로 실행하지 않습니다.

`frontend/` 변경을 main에 push하면 Netlify·Render·EC2의 프런트엔드 배포 대상입니다.
실제 배포는 각 서비스 연결 설정·CI 결과·EC2 접속 정보에 따라 진행됩니다.

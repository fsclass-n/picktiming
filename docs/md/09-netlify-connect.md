# 09. [배포 4단계] Netlify — 프런트엔드 전용 (데모 모드 유지)

https://picktiming.netlify.app 은 **프런트엔드 시연용**으로 유지합니다. 서버·DB와 연결하지 않고,
[`frontend/src/lib/mock.js`](../../frontend/src/lib/mock.js)가 API와 같은 형식의 응답을 브라우저에서 만듭니다.
실제 API 연동은 Render(https://timepick-ai.onrender.com)에서 확인합니다. EC2 운영은 별도 확인이 필요합니다.

## 1. 현재 상태와 확인

기준 커밋 `279a4ce`의 React UI 반영을 확인했습니다. 발표 캡처도 이 사이트의 실제 화면이며,
상품·가격·회원·AI 답변은 데모입니다.

| 확인 항목 | 방법 | 기대 결과 |
|---|---|---|
| 데모 모드 | https://picktiming.netlify.app/js/config.js | `API_BASE_URL: ""` |
| 화면 | https://picktiming.netlify.app | 상단 "데모 모드" 배너, 테스트 로그인 사용 가능 |
| 관리자 화면 | 로그인 페이지의 관리자 테스트 버튼 | 관리자 메뉴 표시, 회원 권한 변경은 조회 전용 제한 |
| 환경 변수 | Site configuration → Environment variables | **`API_BASE_URL`이 없어야 함** |

## 2. 배포 방식

- Netlify → Site configuration → Build & deploy → Continuous deployment에 저장소 `fsclass-n/timepick`이 연결되어 있으면
  **Git 연동**입니다. `frontend/`가 바뀐 커밋이 `main`에 올라오면 Netlify가 [`netlify.toml`](../../netlify.toml)대로
  (`base = "frontend"`, `command = "npm ci && npm run build"`, `publish = "dist"`) 다시 빌드합니다.
  Node는 22를 사용하며 커밋된 `public/js/config.js`의 빈 API 주소가 데모 모드를 결정합니다.
- Git 연동이면 GitHub Secret `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`를 등록하지 않습니다(중복 배포 방지, 10 문서).

## 3. 주의

- 현재 빌드는 환경 변수 `API_BASE_URL`을 읽어 런타임 설정을 다시 생성하지 않습니다.
  실제 동작 기준은 `/js/config.js`의 `window.APP_CONFIG.API_BASE_URL`입니다. 데모 구성을 유지합니다.
- 데모 모드에서 바꾼 데이터(관심 상품 등)는 그 브라우저의 `localStorage`에만 저장됩니다. 다른 브라우저·기기와 공유되지 않습니다.

## 4. 저장소·도메인 변경 후 이전 화면이 남을 때

1. 연결 저장소가 `fsclass-n/timepick`인지, Netlify 앱의 저장소 접근 권한이 있는지 확인합니다.
2. Deploys에서 대상 커밋의 빌드·게시 상태와 게시 잠금을 확인합니다.
3. Base는 `frontend`, 명령은 `npm ci && npm run build`, Publish는 base 기준 `dist`인지 확인합니다.
4. 필요하면 Clear cache and deploy site를 사용하고 새 JS 자산·서비스명·로고가 반영되는지 확인합니다.
5. GitHub 검사 결과와 Netlify 실제 배포 상태는 각각 확인합니다.

다음 문서: [10. GitHub Actions 등록](10-github-actions-setup.md)

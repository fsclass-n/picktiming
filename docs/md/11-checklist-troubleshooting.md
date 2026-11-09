# 11. 최종 점검과 문제 해결

확인 기준: `279a4ce`, 2026-11-05. 아래 체크박스는 환경별 운영자가 확인할 목록입니다.
현재 확인된 검증은 백엔드 51건·RPA 11건·브라우저 9개 시나리오 및 CI입니다.
Netlify·Render 새 UI는 확인했고 EC2 운영은 확인 전입니다.

발표용 점검은 [7분 시연 시나리오](../발표자료/7분_시연시나리오.md)를 사용합니다.
PPT는 170초 대본+10초 전환 여유이며 실제 리허설 시간을 측정해야 합니다.

## 1. 단계별 완료 점검표

### DB · `.env` (06)
- [ ] TiDB Starter 인스턴스 생성, `picktiming` DB 생성, 허용 IP(개발 PC, EC2, Render) 설정
- [ ] 로컬 `.env` 작성: `copy .env.example .env` → `DATABASE_URL`(TiDB), `JWT_SECRET`, `RPA_API_KEY` 채움 (나머지 필수 값은 예시 그대로)
- [ ] 로컬에서 `python -m app.seed` 1회, 데모·관리자 비밀번호 보관
- [ ] `frontend/`에서 `npm ci && npm run build`, 로컬 `uvicorn app.main:app --reload` → http://localhost:8000 화면·로그인 동작

### Render — 프런트엔드·백엔드 분리 (07)
- [ ] Static Site `timepick`: Root Directory `frontend`, Build `npm install && npm run build`, Publish `dist`, Rewrite `/*` → `/index.html`
- [ ] Static Site Environment `VITE_API_URL=https://timepick-api.onrender.com`, `NODE_VERSION=22`, 실제 발급 주소 확인
- [ ] Web Service `picktiming`: Docker, Singapore, Free, Health Check `/health`, Dockerfile Path **`./backend/Dockerfile`**, Build Context `.`
- [ ] Web Service Environment → **Add from .env** + Render 전용 `FRONTEND_URL`(Static Site 실제 주소), `ALLOWED_ORIGINS`에 Static Site 주소 (`FRONTEND_DIR`은 넣지 않음)
- [ ] 두 서비스 Auto-Deploy **After CI Checks Pass**, Build Filter: Static Site `frontend/**` / Web Service `backend/**`, `requirements.txt`, `render.yaml`, `.dockerignore`
- [ ] Static Site 화면 로그인·검색, 데모 배너 없음 / 백엔드 `/health` ok, `/` → Static Site로 302

### EC2 — 단독 풀스택 (08)
- [ ] Elastic IP 연결, DuckDNS가 Elastic IP를 가리킴
- [ ] 보안 그룹 80 개방, 22번은 GitHub Actions 접속 가능하게(10)
- [ ] 로컬 `.env`를 `scp`로 `~/picktiming/.env`에 복사, `chmod 600`
- [ ] `docker compose ps` → api healthy, rpa·web running
- [ ] http://picktiming.duckdns.org/health → ok, 수동 `collect` 성공

### Netlify — 데모 모드 (09)
- [ ] 환경 변수 `API_BASE_URL` 없음, `/js/config.js` → `API_BASE_URL: ""`, 데모 배너 표시

### GitHub Actions (10)
- [ ] Secrets: `RENDER_RPA_API_KEY`(= `.env`의 `RPA_API_KEY`), `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` — `RENDER_DEPLOY_HOOK_URL`은 등록하지 않음
- [ ] Variables: `RENDER_URL` (필요 시 `EC2_APP_DIR`, `EC2_MODE=full`)
- [ ] Git 연동이면 `NETLIFY_*` Secret 미등록
- [ ] Deploy 워크플로 수동 실행 성공, Collect (Render) 수동 실행 성공

### 독립 동작·데이터 흐름 최종 확인
- [ ] KST 00·06·12·18시(07분) 이후 관리자 화면에 `collect_prices` 로그가 추가(GitHub Actions 한 곳, 실제 제품 13종 × 다나와·에누리 = 26건)
- [ ] EC2 `.env`에 `COLLECT_ENABLED`가 없거나 `false` — EC2가 외부 사이트를 중복 수집하지 않음
- [ ] Render와 duckdns 화면에서 같은 계정으로 로그인되고 같은 상품·같은 최신 가격이 보임 (같은 TiDB 공유)
- [ ] EC2를 잠시 멈춰도 Render 화면·API·Actions 수집이 계속 동작 (반대도 동일)

## 2. 자주 나는 문제

| 증상 | 확인할 곳 | 원인 → 해결 |
|---|---|---|
| Render 기동 실패: `운영 환경에서는 jwt_secret, rpa_api_key 값을 반드시 설정해야 합니다` | Render Logs | 해당 환경 변수가 비었거나 기본값 → 입력 |
| `(1045, "Access denied for user ...")` | api 로그 | TiDB 사용자 이름(`xxxx.root` 접두어 포함)·비밀번호 확인, 특수문자 URL 인코딩 |
| `Connections using insecure transport are prohibited` 또는 SSL 오류 | api 로그 | `.env`의 `DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt` 누락(값이 비면 TLS를 쓰지 않음) |
| 로컬에서 `CERTIFICATE_VERIFY_FAILED` | 터미널 | 회사·학원 프록시가 TLS를 가로채는 경우. 다른 네트워크에서 확인하거나 프록시 루트 인증서 파일 경로를 `DB_SSL_CA`에 지정 |
| `(1049, "Unknown database 'picktiming'")` | api 로그 | TiDB에서 `CREATE DATABASE picktiming;` |
| `Can't connect to MySQL server ... timed out` | api 로그 | TiDB 허용 IP 목록에 Render/EC2 IP 없음 |
| `Lost connection to MySQL server during query` (가끔) | api 로그 | TiDB Starter 유휴 연결 정리 — `pool_pre_ping`·`pool_recycle`로 자동 재연결됨. 반복되면 보고 |
| Render `/`가 화면 대신 `{"service":"PickTiming API",...}` JSON | Render Settings | Dockerfile Path가 `./backend/Dockerfile`(API 전용)로 되어 있음 → `./Dockerfile`, Build Context `.` |
| Render 화면이 "데모 모드" 배너로 뜸 | `/js/config.js` | 위와 같은 원인(예전 이미지). 설정 변경 후 재배포 |
| 화면: "API 서버에 연결할 수 없습니다" | 브라우저 F12 콘솔·Network | 같은 도메인 호출이라 CORS 문제는 아님 → `/health` 응답과 서버 로그 확인 |
| Render 첫 화면이 1분 가까이 멈춤 | — | 무료 플랜이 잠들었다 깨는 중. 정상 |
| Netlify가 실제 데이터를 안 보여 줌 | — | 의도된 동작(데모 모드 유지, 09 문서) |
| Netlify에 이전 화면이 보임 | Deploys·GitHub 연결·최신 자산 | 연결 저장소 `fsclass-n/picktiming`, 배포 커밋·게시 상태·`frontend/dist` 설정 확인 |
| 테스트 관리자 권한 변경이 거부됨 | 화면 안내·403 응답 | 조회 전용 제한. 시연에서 실제 회원 권한을 변경하지 않음 |
| 목표가 저장 후 새 알림이 바로 없음 | 관심 상품·다음 수집 | 저장과 가격 도달 알림 생성은 별개. 운영 수집 후 조건을 판정 |
| Collect (Render) 실패: `401 INVALID_RPA_KEY` | Actions 로그 | Secret `RENDER_RPA_API_KEY` ≠ Render `RPA_API_KEY` |
| 수집 결과 `inserted: 0, duplicate: N` | — | 같은 시간대에 다른 수집기(EC2/Actions)가 먼저 저장함. 정상 |
| Render에서 push 후 자동 배포가 안 됨 | Render Events, GitHub 커밋의 검사 결과 | Auto-Deploy = After CI Checks Pass인지, 실패한 검사가 없는지, 바뀐 경로가 Build Filter에 포함되는지 |
| Static Site에서 "API 서버에 연결할 수 없습니다" | 개발자 도구 Console·Network | `CORS` 오류면 백엔드 `FRONTEND_URL`·`ALLOWED_ORIGINS`가 Static Site **실제 주소**와 같은지 확인. 백엔드가 잠들어 있으면 1분 뒤 재시도 |
| Static Site에 데모 배너가 보임 | Static Site Environment | `VITE_API_URL` 누락 → 추가 후 **다시 배포**(빌드 시 들어가는 값) |
| Static Site에서 새로고침하면 404 | Static Site Redirects/Rewrites | `/*` → `/index.html` **Rewrite** 규칙 추가 |
| 백엔드 주소 `/`가 JSON 안내만 응답 | 백엔드 Environment | `FRONTEND_URL` 누락 → 추가하면 화면 경로가 Static Site로 이동 |
| 소셜 로그인 후 백엔드 주소의 404로 이동 | 백엔드 Environment | `FRONTEND_URL` 누락. 콜백(Redirect URI)은 기존 백엔드 주소 그대로 |
| rpa 로그: `Connection refused ... localhost:8000` | `docker compose logs rpa` | EC2 `.env`에서 `RPA_TARGET_API` 줄 삭제(compose 기본값 `http://api:8000` 사용) |
| rpa 로그: `401 ... INVALID_RPA_KEY` | `docker compose logs rpa` | `.env`를 바꾼 뒤 컨테이너를 다시 만들지 않음 → `docker compose up -d` |
| EC2 빌드 중 멈춤·`Killed` | `free -h`, `dmesg` | 메모리 부족 → 스왑 2 GB(08 문서 4단계) 또는 t3.small |
| 관리자 메뉴가 안 보임 | — | 시드의 `admin@picktiming.demo`로 로그인하거나, `ADMIN_EMAILS`에 넣은 이메일로 **새로 가입**(기존 계정은 자동 변경 안 됨) |
| AI 조언이 항상 비슷한 문장 | `/health`의 `"gemini"` | `false`면 키 없음 → 템플릿 문장으로 동작(정상 대체 동작) |
| `429 AI_LIMIT_EXCEEDED` | — | 사용자별 일일 한도(`AI_DAILY_LIMIT`) 초과 |

## 3. 되돌리기

| 대상 | 방법 |
|---|---|
| Netlify | Deploys에서 이전 배포 선택 → **Publish deploy** |
| Render 가격 수집 | Actions → Collect (Render) → ··· → **Disable workflow** (EC2 수집은 계속됨) |
| Render | Events/Deploys에서 이전 배포 **Rollback**(무료 플랜은 최근 2개까지) |
| EC2 | `git log`로 이전 커밋 확인 → 문제 커밋을 GitHub에서 revert해 `main`에 push(자동 재배포). 서버에서 직접 checkout하지 않음 |
| DB | TiDB Starter의 백업·복원 기능 확인. 시드/테스트를 운영 DB에 실행하지 않는 것이 최선 |

## 4. 보안 마무리

- `.env`, `.pem`, TiDB 비밀번호는 Git·메신저 공개 채널에 올리지 않습니다. `.env` 하나가 세 환경 공용이므로 유출 시 영향이 큽니다.
- 값이 노출되면: 로컬 `.env`에서 TiDB 비밀번호(Reset)·`JWT_SECRET`·`RPA_API_KEY`를 교체 → EC2로 다시 `scp`, Render에 다시 붙여 넣기,
  GitHub Secret `RENDER_RPA_API_KEY`도 같은 값으로 교체, EC2 키 페어 교체.
- `python -m app.seed --reset`과 `TEST_DATABASE_URL=<TiDB>` 테스트는 운영 데이터를 지우므로 실행하지 않습니다(일반 `pytest`는 임시 SQLite라 안전).

처음으로: [문서 목록](README.md)

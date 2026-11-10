# 10. [배포 5단계] GitHub Actions 등록 — 자동 배포 + Render 가격 수집

07~09를 마치면 수동 배포는 끝난 상태입니다. 이 단계에서 값을 등록하면
- `main` push 때 **CI 통과 → EC2 자동 배포**(바뀐 폴더에 해당할 때, 05 문서)
- **다나와·에누리 실제 가격 수집 KST 00·06·12·18시**(`collect-render.yml`, 04 문서 — 수집은 이 워크플로 한 곳에서만)

이 동작합니다. 값을 등록하지 않은 대상·작업은 자동으로 건너뜁니다.
Render 배포는 GitHub가 요청하지 않고, Render의 Auto-Deploy(**After CI Checks Pass**)가 CI 통과를 보고 직접 배포합니다(07 문서 3단계).

등록 위치: GitHub `fsclass-n/picktiming` → **Settings → Secrets and variables → Actions** (저장소 관리자 권한 필요)

## 1. Secrets (암호화 저장)

| Name | 값 | 얻는 곳 | 사용처 |
|---|---|---|---|
| `RENDER_RPA_API_KEY` | `.env`의 `RPA_API_KEY`와 **같은 값** | 로컬 `.env` | Render 가격 수집 |
| `EC2_HOST` | `picktiming.duckdns.org` (또는 Elastic IP) | 08 문서 2단계 | 자동 배포 |
| `EC2_USER` | `ubuntu` | Ubuntu AMI 기본 사용자 | 자동 배포 |
| `EC2_SSH_KEY` | `.pem` 파일 **전체 내용** (`-----BEGIN ... KEY-----`부터 `-----END ... KEY-----`까지 줄바꿈 포함) | 08 문서 1단계의 키 페어 | 자동 배포 |
| `DATA_GO_KR_KEY` | `.env`의 같은 이름 값 (선택) | 로컬 `.env` | Render 참가격 수집 |

> `RENDER_DEPLOY_HOOK_URL`은 **등록하지 않습니다**. Render Auto-Deploy(After CI Checks Pass)와 함께 쓰면 같은 커밋이 두 번 배포됩니다.
> (Render Auto-Deploy를 Off로 두고 GitHub가 배포를 요청하게 할 때만 등록)
>
> Netlify가 **Git 연동**이면 `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID`는 등록하지 않습니다. 등록하면 같은 커밋이 두 번 배포됩니다.
> Netlify를 Actions로 배포하려면(수동 업로드 사이트였던 경우) Netlify → User settings → Applications → Personal access token을
> `NETLIFY_AUTH_TOKEN`으로, Site configuration → Site ID를 `NETLIFY_SITE_ID`로 등록하고 Netlify 쪽 Git 연동은 끕니다.

## 2. Variables (평문)

| Name | 값 | 비고 |
|---|---|---|
| `RENDER_URL` | `https://timepick-ai.onrender.com` | Render 가격 수집 대상 (끝에 `/` 없이) |
| `EC2_APP_DIR` | `~/picktiming` | 기본값과 같으면 생략 가능 |
| `EC2_MODE` | `full` | 기본값과 같으면 생략 가능 (`rpa-only`로 두지 않음) |
| `KCA_API_URL` | `.env`의 같은 이름 값 (선택) | Render 참가격 수집 |

`RENDER_HEALTH_URL`은 Deploy Hook 방식에서만 쓰므로 등록하지 않아도 됩니다.

`API_BASE_URL`은 **등록하지 않습니다**(Netlify 데모 모드 유지).

## 3. EC2 보안 그룹 22번 포트 (주의)

배포 작업은 GitHub가 제공하는 러너(매번 다른 공인 IP)에서 EC2로 SSH 접속합니다.
22번을 "내 IP"로만 열어 두면 **EC2 배포가 `Connection timed out`으로 실패**합니다.

| 선택지 | 방법 | 장단점 |
|---|---|---|
| A. 22번을 0.0.0.0/0으로 열기 | 보안 그룹 인바운드 22 → Anywhere | 가장 간단. 비밀번호 로그인은 기본적으로 꺼져 있고 키로만 접속되지만, 무차별 대입 시도가 로그에 쌓임 → 키 파일 관리 철저 |
| B. GitHub Actions IP 대역 허용 | https://api.github.com/meta 의 `actions` 대역 등록 | 대역이 매우 많고 자주 바뀌어 관리가 어려움 |
| C. 자체 호스팅 러너 / AWS SSM | EC2에 러너 설치 또는 SSM 명령으로 배포 | 가장 안전하지만 `deploy.yml` 수정 필요(팀 승인) |

환경에 맞는 접속 범위를 선택합니다. A는 넓은 공개 범위이므로 키 관리·접속 기록 점검과
불필요한 노출 제거가 필요합니다. 현재 구성만으로 C 방식이 구현되었다고 표현하지 않습니다.

## 4. 동작 확인

기준 커밋 `279a4ce`에서 CI는 통과했고 EC2 실제 배포는 건너뛰었습니다.
성공한 작업 안에서도 실제 배포 단계가 실행되었는지 확인합니다.

1. 아무 영향 없는 변경으로 확인하려면 Actions → **Deploy → Run workflow**(수동 실행)에서 대상을 골라 실행합니다.
   수동 실행은 선택한 대상에 **전체 배포**합니다(EC2는 전체 재빌드).
2. 성공 기준

   | 작업 | 기대 결과 |
   |---|---|
   | ci / Backend·RPA·Frontend·Docker | success |
   | 변경 경로 판별 | success |
   | Render (FastAPI) | "RENDER_DEPLOY_HOOK_URL secret이 없어 ... 건너뜁니다" — 정상 (Render가 Auto-Deploy로 직접 배포) |
   | AWS EC2 (docker compose) | `git pull` → `docker compose up` → `{"status":"ok"...}` |
   | Netlify (frontend) | `frontend/` 변경이 없으면 작업 자체가 skipped. 수동 실행 + Git 연동이면 "Netlify Git 연동(netlify.toml)으로 배포하거나 ..." 안내만 출력 — 둘 다 정상 |

3. 이후에는 평소처럼 `main`에 push하면 됩니다.
   - `backend/`를 바꾸면: CI 통과 → Render 자동 배포(Auto-Deploy) + EC2(api) 배포
   - `frontend/`를 바꾸면: Netlify·Render·EC2 모두
   - `docs/`만 바꾸면: 배포 없음 (Render는 Build Filter로 건너뜀)
   - Render 대시보드 → Events에서 "Deploy started for <커밋> after CI checks passed" 같은 기록으로 자동 배포를 확인합니다.
4. **Render 가격 수집 확인**: Actions → **Collect (Render)** → Run workflow → `collect` 실행
   - 성공 기준: "Render 깨우기"에서 `{"status":"ok"...}`, "작업 실행"에서 `카탈로그 동기화: {...}`와 `{'status': 'SUCCESS', 'inserted': 26, 'failed': 0, ...}`
   - `failed`가 있으면 로그의 `HTTP 403`(사이트가 Actions IP를 거부) 또는 "가격을 읽지 못한 판매처"(구조 변경)를 확인합니다. 우회하지 않습니다(04 문서 4절).
   - 예약 실행은 매시 07분에 돌지만 수집은 KST 00·06·12·18시에만 하고, 그 밖의 시각은 03시 재학습 등 해당 작업이 있을 때만 Render를 깨웁니다(몇 분 늦을 수 있음).
   - 공개 저장소에 60일간 활동이 없으면 GitHub가 예약 실행을 멈춥니다. 그때는 이 화면에서 **Enable workflow**를 누릅니다.

## 5. 실패했을 때

| 단계 | 메시지 | 원인·해결 |
|---|---|---|
| EC2 | `Permission denied (publickey)` | `EC2_SSH_KEY` 내용 잘림/다른 키, `EC2_USER` 오타 |
| EC2 | `Connection timed out` | 보안 그룹 22번(3단계), `EC2_HOST` 오타, 인스턴스 중지 상태 |
| EC2 | `fatal: Not possible to fast-forward` | 서버에서 추적 파일을 직접 수정함 → 서버에서 `git status` 확인 후 되돌림 |
| Render | push했는데 배포가 안 됨 | Auto-Deploy가 After CI Checks Pass인지, 그 커밋의 GitHub 검사 중 실패한 것이 없는지, 바뀐 경로가 Build Filter에 포함되는지 확인 |
| Render | 같은 커밋이 두 번 배포됨 | `RENDER_DEPLOY_HOOK_URL` Secret 삭제 |
| Render | 배포 후 기동 실패 | Render Logs 확인 — DB 접속 값, `JWT_SECRET`·`RPA_API_KEY` 누락 |
| Collect (Render) | "실행할 작업 결정"에서 건너뜀 안내 | Variable `RENDER_URL` 또는 Secret `RENDER_RPA_API_KEY` 미등록 |
| Collect (Render) | `401 ... INVALID_RPA_KEY` | `RENDER_RPA_API_KEY`가 Render의 `RPA_API_KEY`와 다름 |
| Collect (Render) | `Render 헬스 체크 실패` | Render 서비스 중지·배포 실패, `RENDER_URL` 오타 |

다음 문서: [11. 최종 점검과 문제 해결](11-checklist-troubleshooting.md)

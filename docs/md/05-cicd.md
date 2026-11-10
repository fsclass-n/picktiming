# 05. CI/CD 파이프라인 (GitHub Actions)

소스: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml),
[`.github/workflows/collect-render.yml`](../../.github/workflows/collect-render.yml), [`.github/scripts/detect-changes.sh`](../../.github/scripts/detect-changes.sh)

## 1. 언제 무엇이 도는가

| 이벤트 | 워크플로 | 내용 |
|---|---|---|
| `main` 외 브랜치 push, Pull Request | `ci.yml` | 검사만 (배포 없음) |
| `main` push | `deploy.yml` | `ci.yml` 전체 통과 → **바뀐 폴더에 해당하는 대상만** 배포 |
| 수동 실행 (Actions → Deploy → Run workflow) | `deploy.yml` | 체크한 대상(Netlify/Render/EC2)에 전체 배포 |
| 매시 07분 예약 실행 / 수동 실행 | `collect-render.yml` | **다나와·에누리 실제 가격 수집**(KST 00·06·12·18시만, 유일한 수집 경로) + 03시 재학습, 06시 참가격, 월 07시 리포트 |

## 2. CI 작업 (`ci.yml`)

| 작업 | 내용 |
|---|---|
| Backend (lint · pytest on SQLite) | `ruff check backend`, `pytest` |
| Backend (pytest on MySQL 8) | MySQL 8.0 서비스 컨테이너에서 같은 테스트 (TiDB 호환성 사전 확인) |
| RPA (lint · pytest) | `ruff check rpa`, `pytest` |
| Frontend | `npm ci`·React 프로덕션 빌드, SPA 진입점·데모 설정 확인, **`VITE_API_URL` 주입·끝 `/` 정리·잘못된 주소 빌드 실패** 확인 |
| Docker build | api·rpa 이미지 빌드·`/health` 확인, **Render 백엔드 구성(API 이미지 + `FRONTEND_URL`) 화면 경로 302·API 404·CORS 사전 요청 확인**, 롤백용 통합 이미지의 `/`·`/js/config.js` 확인, `docker compose config` 검증 |

## 3. 배포 대상 판별 (`detect-changes.sh`)

직전 push와 비교해 바뀐 파일 경로로 대상을 정합니다.

| 바뀐 경로 | Netlify | Render | EC2 (full) |
|---|:---:|:---:|:---:|
| `frontend/` | ✅ | ✅ (풀스택 이미지에 포함) | ✅ (web 이미지 재빌드) |
| `netlify.toml` | ✅ | – | – |
| `backend/` | – | ✅ | ✅ (api만 재빌드) |
| `render.yaml`, `.dockerignore`(루트) | – | ✅ | – |
| `Dockerfile`(루트) | – | ✅ | – |
| `requirements.txt` | – | ✅ | ✅ (api·rpa 재빌드) |
| `rpa/` | – | – | ✅ (rpa만 재빌드) |
| `docker-compose.yml` | – | – | ✅ (전체 재빌드) |
| `deploy/` | – | – | ✅ (web 이미지 재빌드) |
| 그 외 (`docs/`, `README.md`, `.claude/`, 워크플로 등) | – | – | – |

- EC2는 **full 모드**(nginx + api + rpa)입니다. `EC2_MODE` 변수는 등록하지 않거나 `full`로 둡니다.
- Render와 EC2가 함께 배포될 때는 Render를 먼저 배포한 뒤 EC2를 배포합니다.
- 비교 기준 커밋이 없는 첫 push·강제 push는 모든 대상에 배포합니다.
- Netlify는 데모 모드라 배포되어도 화면만 바뀌고 서버와는 무관합니다.

로컬에서 미리 확인:

```bash
CHANGED_FILES="backend/app/main.py" EVENT=push bash .github/scripts/detect-changes.sh
```

## 4. 대상별 배포 방식

| 대상 | 방식 | 필요한 값 (없으면 그 대상만 건너뜀) |
|---|---|---|
| Render | **Render Auto-Deploy "After CI Checks Pass"**: GitHub 검사 통과 후 직접 배포(Build Filter: `backend/**`, `frontend/**`, `Dockerfile`, `requirements.txt`, `render.yaml`, `.dockerignore`). `deploy.yml`의 Render 작업은 Hook이 없으면 건너뜀 | Render 대시보드 설정(07 문서). `RENDER_DEPLOY_HOOK_URL`은 등록하지 않음(Auto-Deploy Off일 때만 사용) |
| EC2 | SSH 접속 → `git pull --ff-only origin main` → 바뀐 서비스만 `docker compose up -d --build` → `http://localhost/health` 확인 | Secrets `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`, Variable `EC2_APP_DIR`(기본 `~/timepick`) |
| Netlify | (Actions 방식) React 빌드 결과 `frontend/dist`를 zip으로 Netlify API에 업로드 | Secrets `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID` |

> Netlify는 **Git 연동(Netlify가 저장소를 직접 빌드)과 Actions 방식 중 하나만** 씁니다. 이미 Git 연동으로 배포했다면
> `NETLIFY_*` Secret을 등록하지 않습니다(중복 배포 방지). 데모 모드 유지를 위해 `API_BASE_URL`은 어디에도 등록하지 않습니다.

## 5. Render용 가격 수집 (`collect-render.yml`)

| 단계 | 내용 |
|---|---|
| 실행할 작업 결정 | `RENDER_URL`·`RENDER_RPA_API_KEY`가 없으면 건너뜀. KST 시각으로 `collect` + (`train` / `public` / `report`) 결정 |
| Render 깨우기 | `/health`를 10초 간격으로 최대 18회 호출 (무료 플랜 잠듦 대응) |
| 작업 실행 | `rpa/`에서 `python -m collector.jobs <작업>` — EC2 수집기와 같은 코드 |
| 리포트 보관 | `report`가 있으면 엑셀을 Actions 아티팩트로 30일 보관 |

- GitHub 예약 실행은 몇 분 늦게 시작될 수 있습니다(정각 혼잡을 피해 07분에 실행).
- 공개 저장소에서 **60일간 저장소 활동이 없으면 예약 워크플로가 자동으로 꺼집니다**. Actions 화면에서 다시 켭니다.

다음 문서: [06. DB 준비](06-database.md)

## 6. 최근 확인과 결과 해석

기준 커밋 `279a4ce`, [Deploy 41947934806](https://github.com/fsclass-n/timepick/actions/runs/41947934806)의
React·백엔드 SQLite/MySQL·RPA·Docker 검사가 통과했습니다.
브라우저 9개 시나리오는 별도 로컬 검사이며 CI에 자동 연결되어 있다고 표현하지 않습니다.

배포 작업의 초록색 상태만으로 실제 배포를 단정하지 않습니다. 키가 없을 때 건너뜀 안내만 성공할 수 있습니다.
Netlify·Render는 실제 서비스의 새 UI 자산을 확인했고 EC2의 SSH 배포는 건너뛴 상태입니다.
`docs/`만 바꾸는 이번 문서 작업은 앱 배포 대상이 아닙니다.

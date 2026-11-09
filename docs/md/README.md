# PickTiming 문서 모음 — 프로젝트 파악 → 배포까지

이 폴더는 픽타이밍 프로젝트 전체를 이해하고, **GitHub를 통해 Render(프런트엔드·백엔드 분리)와 AWS EC2(단독 풀스택)에 각각 배포**하기 위한 단계별 문서입니다.
번호 순서대로 읽고 진행하면 됩니다.

문서 개정 기준: `279a4ce`, 2026-11-05. 현재 구조는 아래 운영 문서,
검증·미확인 상태는 이 목록, 이전 자료의 정정 사유는 최종 발표 수정 보고서를 기준으로 봅니다.

## 최종 발표와 제출 파일

- [발표·기술 면접 포트폴리오 PPT](../프로젝트_발표자료.pptx) · [PDF](../pdf/프로젝트_발표자료.pdf) (18장)
- [10분 발표·시연 영상 제작 프롬프트](../발표자료/영상제작_프롬프트.md) · [영상 대본·연출 가이드](../video/영상_대본_및_연출가이드.md)
- [3분 발표 대본](../발표자료/3분_발표대본.md) · [7분 시연 시나리오](../발표자료/7분_시연시나리오.md)
- [제작 기준·확인 근거](../발표자료/제작기준.md) · [수정 보고서](../발표자료/수정사항_보고서.md)
- 단계별 산출물은 `docs/산출물/`, 진행일지는 `docs/`, PDF는 `docs/pdf/`에 있습니다.
  원본 일정은 계획으로 유지하고 미확인 회의·성과·발표 기록은 완료 사실에서 제외합니다.

## 목표 구성 (확정)

| 구분 | 주소 | 역할 | 상태 |
|---|---|---|---|
| Netlify | https://picktiming.netlify.app | **프런트엔드 전용 — 데모 모드** | 새 UI 배포 확인 |
| 로컬 PC | http://localhost:8000 | FastAPI가 빌드한 React + API 제공 | 운영 DB 사용 시 데이터 변경 주의 |
| Render 프런트엔드 | https://picktiming-web.onrender.com | **Static Site**: React 빌드 결과, `VITE_API_URL`로 백엔드 호출 | 분리 전환 진행(07 문서) |
| Render 백엔드 | https://picktiming.onrender.com | **Web Service**: FastAPI API·AI·수집 수신 (Docker, 무료 플랜). 화면 경로는 Static Site로 이동 | 기존 주소 유지 |
| AWS EC2 | http://picktiming.duckdns.org | **단독 풀스택 구성**: nginx + FastAPI + RPA | 실제 운영 확인 전 |
| TiDB Cloud | (TiDB 접속 주소) | **유일한 DB — 로컬·Render·EC2가 같은 DB를 공유** | DB 생성 완료 |
| MySQL 8 | GitHub Actions CI | MySQL 호환성 자동 테스트 전용 | CI에 이미 구성됨 |
| GitHub Actions | — | CI/CD + **다나와·에누리 실제 가격 수집(KST 00·06·12·18시, 수집은 이곳 한 곳)** | CI 통과, 대상별 실제 배포 단계 별도 확인 |

**설정 파일은 `.env` 하나**: 로컬에서 작성 → EC2로 `scp` 복사 → Render는 Environment → "Add from .env"로 같은 내용을 붙여 넣기.

```
 사용자 ──▶ Netlify  (frontend only, 데모 모드 — API 호출 없음)

 사용자 ──▶ Render Static Site  https://picktiming-web.onrender.com      사용자 ──▶ EC2  http://picktiming.duckdns.org
                     │ VITE_API_URL (CORS 허용)                             ┌───────────────────────────────────┐
                     ▼                                                       │ nginx(프런트) ─▶ api ◀─ rpa(학습) │
            Render Web Service  https://picktiming.onrender.com             └─────────────────┬─────────────────┘
            ┌──────────────────────────────┐                                                  │
            │ FastAPI = API 전용            │                                                  │
            └──────────────┬───────────────┘                                                  │
                 ▲         │                                                                  │
 GitHub Actions  │         └───────────────▶  TiDB Cloud (운영 DB 하나를 공유)  ◀──────────┘
 collect-render  │                            같은 시간대 같은 판매처 가격은 한 번만 저장
 (하루 4회 수집) ─┘
```

- **독립 구성**: Render와 EC2는 서로를 호출하지 않습니다. 두 환경의 운영이 확인되면 독립적으로 사용할 수 있습니다.
- **가격 수집 두 갈래**: EC2는 자체 `rpa` 컨테이너, Render는 GitHub Actions 예약 실행(`collect-render.yml`)이 수집기를 돌립니다.
  둘 다 같은 TiDB에 저장하므로, API가 **같은 판매처·같은 시간대(정시~59분)의 두 번째 가격은 건너뜁니다**(중복 저장 방지).
- **데이터 공유**: 회원·관심 상품·가격 이력이 공유되므로 어느 주소로 접속해도 같은 데이터가 보입니다.

## 문서 목록

### A. 프로젝트 파악

| 번호 | 문서 | 내용 |
|---|---|---|
| 01 | [프로젝트 개요와 구조](01-project-overview.md) | 서비스 흐름, 기술 스택, 폴더 구조, 환경별 차이 |
| 02 | [백엔드(FastAPI)](02-backend.md) | 설정(환경 변수), DB 테이블 12개, API 목록, 프런트엔드 서빙, AI·ML |
| 03 | [프런트엔드](03-frontend.md) | React 통합 UI·가입·차트·알림, 데모/운영 연동 |
| 04 | [RPA 수집기](04-rpa.md) | 수집 작업 4종, EC2 컨테이너와 GitHub Actions 두 실행 경로 |
| 05 | [CI/CD 파이프라인](05-cicd.md) | `ci.yml`, `deploy.yml`, `collect-render.yml`, 바뀐 폴더별 배포 판별 |

### B. 배포 진행 (이 순서대로)

| 번호 | 문서 | 할 일 |
|---|---|---|
| 06 | [DB 준비: TiDB 공용 · `.env` 작성](06-database.md) | TiDB 접속 문자열, 로컬 `.env`, 시드 데이터 |
| 07 | [Render 배포 (프런트엔드·백엔드 분리)](07-deploy-render.md) | Static Site·Web Service 설정, 무중단 전환 순서, 확인·되돌리기 |
| 08 | [EC2 배포 (단독 풀스택, DuckDNS)](08-deploy-ec2.md) | 인스턴스·고정 IP·DuckDNS·Docker·`.env`·시드 |
| 09 | [Netlify (데모 모드 유지)](09-netlify-connect.md) | React 빌드·저장소 연결·게시 상태 확인 |
| 10 | [GitHub Actions 등록 (자동 배포 + Render 수집)](10-github-actions-setup.md) | Secrets·Variables 등록, 첫 실행 확인 |
| 11 | [최종 점검과 문제 해결](11-checklist-troubleshooting.md) | 점검표, 자주 나는 오류와 해결법 |

## 이 프로젝트에서 특히 주의할 점 (요약)

1. **`main`에 push하면 운영 배포**가 일어납니다. CI가 통과하면 Render는 Auto-Deploy(After CI Checks Pass)로, EC2는 GitHub Actions로 배포됩니다(05·07 참고).
2. **로컬 포함 모든 환경이 같은 TiDB**를 씁니다. 로컬에서 바꾼 데이터가 곧 운영 데이터입니다.
   `python -m app.seed --reset`, `TEST_DATABASE_URL=<TiDB>` 테스트는 **운영 데이터를 모두 지웁니다**(일반 `pytest`는 임시 SQLite라 안전).
3. **`.env` 하나를 세 환경에서 공용**으로 씁니다([`.env.example`](../../.env.example)). 로컬 작성 → EC2로 `scp` → Render에 "Add from .env"로 붙여 넣기.
   값을 바꾸면 세 곳 모두 다시 반영합니다. `FRONTEND_DIR`, `RPA_TARGET_API`, Render 전용 `FRONTEND_URL`·`VITE_API_URL`은 `.env`에 넣지 않습니다.
4. Render 무료 플랜은 **셸(Shell) 접속이 안 됩니다**. 시드 데이터는 로컬 PC에서 TiDB로 넣습니다(06 문서).
5. GitHub Actions가 EC2에 SSH로 접속하므로 **보안 그룹 22번 포트를 GitHub 러너가 접근할 수 있게** 열어야 합니다(10 참고).
6. 공개 저장소의 예약 워크플로는 **저장소에 60일간 활동이 없으면 GitHub가 자동으로 멈춥니다**. 멈추면 Actions 화면에서 다시 켭니다.

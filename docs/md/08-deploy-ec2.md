# 08. [배포 3단계] AWS EC2 — 단독 풀스택 (http://picktiming.duckdns.org)

EC2 한 대에서 [`docker-compose.yml`](../../docker-compose.yml)의 세 컨테이너로 화면·API·가격 수집을 운영하도록 구성합니다.
Render를 호출하지 않으며, DB만 **TiDB**(Render와 공유)를 씁니다.

현재는 배포 코드가 준비된 상태이며, 기준 커밋 `279a4ce`의 실제 SSH 배포는 건너뛰었습니다.
아래 절차와 확인을 마치기 전에는 EC2 운영 완료로 발표하지 않습니다.

| 컨테이너 | 역할 |
|---|---|
| `web` (deploy/web.Dockerfile) | React를 빌드해 nginx로 제공. `/api`, `/docs`, `/health`를 `api`로 프록시 |
| `api` (backend 이미지) | FastAPI, TiDB 접속 |
| `rpa` (rpa 이미지) | 스케줄러 — 매시 수집 등, `http://api:8000` 호출 |

## 1. EC2 인스턴스 만들기

| 항목 | 권장값 |
|---|---|
| AMI | Ubuntu Server 24.04 LTS (22.04도 가능) |
| 인스턴스 유형 | t3.small(2 GB) 권장. 프리 티어 t2/t3.micro(1 GB)도 가능하나 **스왑 2 GB 필수**(아래 4단계) |
| 키 페어 | 새로 생성(.pem) → 안전하게 보관. GitHub Actions에도 등록함(10 문서) |
| 스토리지 | 20 GB 이상 (web·api·rpa 이미지 + 빌드 캐시) |
| 보안 그룹 인바운드 | 22(SSH), 80(HTTP, 0.0.0.0/0), 443(HTTPS 구성 시) — 22번은 10 문서의 주의사항 참고 |

## 2. 고정 IP와 DuckDNS

1. EC2 → **Elastic IP** 할당 → 인스턴스에 연결 (재시작해도 IP가 바뀌지 않게)
2. https://www.duckdns.org 로그인 → 서브도메인 `timepick`의 **current ip**를 Elastic IP로 입력 → update ip
3. PC에서 확인: `nslookup picktiming.duckdns.org` → Elastic IP가 나오면 성공
4. TiDB의 허용 IP 목록이 있다면 이 Elastic IP를 추가(06 문서)

## 3. 접속

```bash
ssh -i timepick.pem ubuntu@picktiming.duckdns.org
```

## 4. (micro 인스턴스만) 스왑 2 GB 만들기

pandas·scikit-learn 이미지 빌드와 실행에 메모리가 부족할 수 있습니다.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## 5. 저장소 받기 + Docker 설치 ([`deploy/ec2-setup.sh`](../../deploy/ec2-setup.sh))

스크립트는 상태에 따라 한 단계씩 진행합니다. 여기서 **두 번** 실행하고, 기동은 6단계(.env 작성) 후 7단계에서 직접 합니다.

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/fsclass-n/timepick.git ~/timepick

# 1회차: Docker 설치 후 종료 → 로그아웃했다가 다시 SSH 접속(docker 그룹 적용)
bash ~/timepick/deploy/ec2-setup.sh https://github.com/fsclass-n/timepick.git
exit

# 2회차: .env.example을 복사해 ~/timepick/.env를 만들고 종료
bash ~/timepick/deploy/ec2-setup.sh https://github.com/fsclass-n/timepick.git
```

## 6. `.env` — 로컬 PC의 `.env`를 그대로 복사 (가장 중요)

로컬·Render와 **같은 `.env`** 를 씁니다. 값을 서버에서 다시 입력하지 않고, PC의 파일을 그대로 올립니다.

PC(PowerShell, 저장소 폴더)에서:
```powershell
scp -i <키.pem 경로> .env ubuntu@picktiming.duckdns.org:~/timepick/.env
```
EC2에서:
```bash
chmod 600 ~/timepick/.env
grep -c . ~/timepick/.env          # 줄 수 확인(빈 파일이 아닌지)
```

- `ec2-setup.sh` 2회차가 만든 예시 `.env`는 이 복사로 덮어씁니다.
- `.env` 값을 바꾸면 PC에서 다시 `scp` → EC2에서 `docker compose up -d`(변경된 값으로 컨테이너 재생성), Render에도 다시 붙여 넣습니다(07 문서).
- `RPA_TARGET_API`, `FRONTEND_DIR`은 `.env`에 넣지 않습니다. EC2 수집기는 compose 기본값 `http://api:8000`, 화면은 nginx가 담당합니다.
- 값에 `$`가 들어 있으면 compose가 변수로 해석합니다. 그런 값은 작은따옴표로 감쌉니다(`JWT_SECRET='ab$cd'`).

## 7. 기동

```bash
cd ~/timepick
docker compose config -q && echo "compose OK"      # .env 검증
docker compose up -d --build                         # 첫 빌드는 수 분 소요
docker compose ps                                    # api: healthy, rpa·web: running
curl -fsS http://localhost/health                    # {"status":"ok","env":"production",...}
```

PC 브라우저: http://picktiming.duckdns.org (프런트엔드), http://picktiming.duckdns.org/docs (API 문서)

## 8. 시드 데이터 (TiDB에 아직 데이터가 없을 때 1회)

보통은 06 문서 4단계에서 로컬 PC로 이미 넣었으므로 생략합니다. EC2에서 넣어야 한다면:

```bash
docker compose exec api python -m app.seed      # .env의 SEED_* 값 사용, 데이터가 있으면 자동으로 건너뜀
```

TiDB를 로컬·Render와 공유하므로 한 번만 넣으면 모든 환경에서 보입니다.

## 9. RPA 동작 확인

```bash
docker compose logs -f rpa                                   # "scheduler started (tz=Asia/Seoul, api=http://api:8000)"
docker compose exec rpa python -m collector.jobs collect     # 즉시 1회 수집 → {'status': 'SUCCESS', 'inserted': 36, 'duplicate': 0, ...} (시드 기준 12상품 × 3쇼핑몰)
# 같은 시간대에 Render용 Actions 수집이 먼저 돌았다면 'inserted': 0, 'duplicate': 36 — 중복 방지가 동작한 것(정상)
```

관리자 계정으로 로그인 → 관리자 화면에서 수집 로그가 쌓이는지 확인합니다.

## 10. 운영 명령 모음

| 목적 | 명령 |
|---|---|
| 로그 | `docker compose logs -f --tail 100 api` (rpa, web) |
| 재시작 | `docker compose restart api` |
| 수동 업데이트 | `git pull --ff-only origin main && docker compose up -d --build` |
| 디스크 정리 | `docker image prune -f`, 확인 `df -h` |
| 주간 리포트 | `ls ~/timepick/reports/` |

- 서버에서 저장소 파일(추적 대상)을 직접 수정하지 않습니다. 자동 배포의 `git pull --ff-only`가 실패합니다. 설정은 `.env`(Git 제외)에서만 바꿉니다.

## 11. (선택) HTTPS 구성

EC2는 HTTP만으로도 동작하지만, http://picktiming.duckdns.org 화면은 로그인 비밀번호가 암호화되지 않은 채 전송되므로
시연·운영 전에 HTTPS를 권장합니다. HTTPS로 바꾸면 `.env`의 `ALLOWED_ORIGINS`도 `https://picktiming.duckdns.org`로 바꿉니다.

- 방법: Let's Encrypt(certbot)로 `picktiming.duckdns.org` 인증서 발급 → nginx에 443 서버 블록 추가·80→443 리다이렉트 →
  compose `web`에 `443:443` 포트와 인증서 볼륨 추가 → 보안 그룹 443 열기 → 인증서 자동 갱신 설정
- `deploy/nginx.conf`, `docker-compose.yml`을 바꾸는 작업이므로(EC2 전체 재배포 발생) 별도 작업으로 팀 승인 후 진행합니다.

다음 문서: [09. Netlify (데모 모드 유지)](09-netlify-connect.md)

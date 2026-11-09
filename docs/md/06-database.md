# 06. [배포 1단계] DB 준비 — TiDB 하나를 로컬·Render·EC2가 공유

이 문서는 구성·이동 절차입니다. 문서 갱신만으로 DB가 변경되지는 않습니다.
발표에는 운영 DB 연결과 스키마 이름 변경 완료를 구분해 기록합니다.
회원 정보·가격 데이터가 들어 있는 운영 DB를 발표용 초기화 대상으로 사용하지 않습니다.

## 1. 역할 정리

| DB | 용도 | 사용하는 곳 |
|---|---|---|
| **TiDB Cloud Starter** | **유일한 운영 DB** | 로컬 PC, Render, EC2 — 모두 같은 `.env`의 같은 `DATABASE_URL` |
| SQLite (임시 파일) | 자동 테스트 | `pytest` (로컬·CI). `.env`의 TiDB 값을 쓰지 않음 |
| MySQL 8 | MySQL 호환성 테스트 | GitHub Actions CI에서만 (서비스 컨테이너, 자동) |

- 백엔드는 `DATABASE_URL`만 보고 SQLite / MySQL·TiDB를 구분합니다([`database.py`](../../backend/app/database.py)).
- `DB_SSL_CA`에 값이 있으면 TLS로 접속하고 인증서·호스트 이름을 검증합니다. 그 경로의 파일이 없는 환경(Windows 로컬)은
  자동으로 certifi 인증서 묶음을 사용하므로, **로컬·EC2·Render 모두 같은 값**(`/etc/ssl/certs/ca-certificates.crt`)을 씁니다.
- 연결은 280초마다 재생성(`pool_recycle=280`)되어, 유휴 연결을 끊는 TiDB Starter의 특성(공식 문서 권장값 300초)에 맞춰져 있습니다.

## 2. TiDB Cloud 준비

1. https://tidbcloud.com → **Starter**(무료) 인스턴스 생성
   - 리전: Render 서비스가 `singapore`이므로 **AWS Singapore**를 권장합니다.
   - 무료 한도(인스턴스당): 행 저장소 5 GiB, 월 5,000만 RU. 이 프로젝트 규모에는 충분합니다.
2. 인스턴스 → 우측 상단 **Connect**
   - Connection Type: `Public`, Connect With: `General`
   - **Generate Password** → 안전한 곳에 보관(다시 볼 수 없음)
   - 표시되는 값: `HOST`(예: `gateway01.<리전>.prod.aws.tidbcloud.com`), `PORT`(4000), `USER`(예: `xxxxxxxx.root`)
3. 접근 허용 IP(IP Access List / Firewall 규칙)가 보이면 허용합니다: 개발 PC 공인 IP, EC2 Elastic IP, Render(고정 IP 없음 → Render 대시보드 Connect → Outbound의 IP 범위, 또는 전체 허용)
4. **SQL Editor**에서 DB 생성 (기본 DB는 `test`이므로 반드시 만듦)
   ```sql
   CREATE DATABASE picktiming;
   ```
   테이블은 API가 처음 기동할 때 자동 생성됩니다.

## 3. `.env`에 넣기 (로컬·EC2·Render 공용)

```dotenv
DATABASE_URL=mysql+pymysql://<USER>:<PASSWORD>@<HOST>:4000/timepick?charset=utf8mb4
DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt
```

- 예: `mysql+pymysql://abcd1234.root:p%40ss@gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000/timepick?charset=utf8mb4`
- 비밀번호에 `@ : / ? # %` 같은 특수문자가 있으면 **URL 인코딩**합니다(`@` → `%40`):
  `python -c "import urllib.parse;print(urllib.parse.quote('비밀번호', safe=''))"`
- Connect With를 `SQLAlchemy`로 고르면 완성된 주소를 보여 주지만, 끝의 `?ssl_ca=...` 부분은 지우고 `?charset=utf8mb4`로 바꿉니다
  (그 경로는 지금 PC 기준이라 다른 환경에서 동작하지 않음 — TLS는 `DB_SSL_CA`가 담당).
- `.env` 전체 구성은 [`.env.example`](../../.env.example), 환경별 복사 방법은 07(Render)·08(EC2) 문서를 따릅니다.

## 4. 시드 데이터 넣기 (최초 1회)

로컬 `.env`가 TiDB를 가리키므로 **로컬 PC에서 바로** 넣을 수 있습니다. 데이터가 이미 있으면 자동으로 건너뜁니다.

```powershell
cd E:\wi\git\picktiming
.venv\Scripts\activate
cd backend
python -m app.seed          # 데모·관리자 계정 비밀번호가 화면에 출력됨 (.env의 SEED_* 값이 있으면 그 값)
```

EC2에서 넣을 때: `docker compose exec api python -m app.seed`

## 5. 운영 DB를 공유하므로 반드시 지킬 것

| 하면 안 되는 것 | 이유 |
|---|---|
| `python -m app.seed --reset` | 모든 테이블을 삭제합니다(운영 데이터 전체 삭제) |
| `TEST_DATABASE_URL`에 TiDB 주소를 넣고 `pytest` | 테스트가 시작할 때 DB를 초기화합니다 |
| 로컬에서 DB 구조를 바꾸는 실험 | Render·EC2가 같은 DB를 쓰는 중입니다 |

- 그냥 `pytest`를 실행하는 것은 안전합니다. 테스트 설정([`conftest.py`](../../backend/tests/conftest.py))이 `DATABASE_URL`을 임시 SQLite로 덮어씁니다.
- 로컬에서 수집기(`python -m collector.jobs collect`)를 돌리면 운영 DB에 가격이 저장됩니다. 같은 시간대 중복은 API가 건너뜁니다.
- 실험용 DB가 필요하면 같은 TiDB 인스턴스에 `CREATE DATABASE picktiming_dev;`를 만들고, 로컬 `.env`의 주소 끝만 `/picktiming_dev`로 바꿔 씁니다.

## 6. TiDB 사용 시 코드 작성 주의

- CI가 SQLite와 MySQL 8 양쪽에서 테스트하므로, 두 곳에서 통과하는 SQL은 TiDB에서도 대부분 동작합니다.
- TiDB 한 행 최대 6 MiB(기본). 모델 바이너리는 약 0.24 MiB로 여유가 있습니다.
- TiDB 트랜잭션은 30분을 넘길 수 없습니다. 대량 작업은 나눠서 커밋합니다.
- TiDB의 `AUTO_INCREMENT` 값은 증가는 하지만 연속이 아닐 수 있습니다. ID가 1, 2, 3…으로 이어진다고 가정하지 않습니다.

다음 문서: [07. Render 배포](07-deploy-render.md)

## 7. DB 이름 변경 기록 (buytiming → picktiming)

TiDB·MySQL은 `ALTER DATABASE ... RENAME`을 지원하지 않는다(문법 오류). 새 DB를 만들고 테이블을 `RENAME TABLE`로 옮긴다.
데이터는 복사되지 않고 이동만 하므로 빠르고, 행·인덱스·AUTO_INCREMENT 값이 그대로 유지된다.

```sql
CREATE DATABASE IF NOT EXISTS picktiming;
RENAME TABLE buytiming.users TO picktiming.users;
RENAME TABLE buytiming.products TO picktiming.products;
RENAME TABLE buytiming.malls TO picktiming.malls;
RENAME TABLE buytiming.product_listings TO picktiming.product_listings;
RENAME TABLE buytiming.price_history TO picktiming.price_history;
RENAME TABLE buytiming.public_prices TO picktiming.public_prices;
RENAME TABLE buytiming.watchlist TO picktiming.watchlist;
RENAME TABLE buytiming.alerts TO picktiming.alerts;
RENAME TABLE buytiming.timing_predictions TO picktiming.timing_predictions;
RENAME TABLE buytiming.ai_advice_logs TO picktiming.ai_advice_logs;
RENAME TABLE buytiming.model_versions TO picktiming.model_versions;
RENAME TABLE buytiming.rpa_job_logs TO picktiming.rpa_job_logs;
```

- 확인: `SHOW TABLES FROM buytiming;`이 비어 있고 `SELECT COUNT(*) FROM picktiming.users;`가 이전과 같아야 한다.
- 이어서 `DATABASE_URL` 끝의 DB 이름을 `picktiming`으로 바꾼다: 로컬 `.env` → Render Environment → EC2 `.env`.
  Render가 이전 주소로 다시 시작하면 서버 시작 시 `buytiming`에 빈 테이블을 새로 만들 수 있으니 Render 값을 바로 바꾼다.
- 빈 `buytiming`은 위 확인 후에만 `DROP DATABASE buytiming;`으로 지운다(되돌릴 수 없음).

## 8. DB 이름 변경 기록 (picktiming → timepick, 2026-11-09)

서비스 주소를 `timepick`(Static Site)·`timepick-api`(Web Service)로 바꾸면서 DB 이름도 같은 방식(7절 SQL의 `buytiming`→`picktiming`, `picktiming`→`timepick`)으로 옮겼다.

- 확인: `timepick`에 테이블 12개, `users` 3·`products` 25·`price_history` 5,417건(변경 전과 동일), `picktiming`은 없음(접속 시 1049).
- `DATABASE_URL` 경로를 `/timepick`으로: 로컬 `.env`, Render `timepick-api`, EC2 `.env`. 예전 Render 서비스(`picktiming`)는 경로가 `/picktiming`이라 더 이상 시작하지 않으므로 Suspend한다.

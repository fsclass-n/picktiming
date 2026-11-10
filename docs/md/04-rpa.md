# 04. RPA 수집기 — 다나와·에누리 실제 가격 수집

소스: [`rpa/collector/`](../../rpa/collector). 실제 판매 가격을 **GitHub Actions 한 곳에서만** 수집해 Render API로 보내고,
공용 TiDB에 저장하므로 Render·EC2 화면 모두 같은 가격을 보여 줍니다.

| 실행 위치 | 하는 일 | 보내는 곳 |
|---|---|---|
| **GitHub Actions** ([`collect-render.yml`](../../.github/workflows/collect-render.yml)) | 가격 수집 KST 00·06·12·18시(매시 07분 예약 중 해당 시각만), 03시 재학습, 06시 참가격, 월 07시 리포트 | `https://timepick-ai.onrender.com` (Render API, Secret `RENDER_RPA_API_KEY`) |
| EC2 `rpa` 컨테이너 ([`scheduler.py`](../../rpa/collector/scheduler.py)) | 재학습·참가격·리포트만. **외부 사이트 수집은 하지 않음**(`COLLECT_ENABLED=false`, compose 기본값) | `http://api:8000` |

- 수집 위치를 한 곳으로 정해 **같은 사이트에 이중 접속하지 않습니다**. EC2에서 직접 수집하려면 EC2 `.env`에 `COLLECT_ENABLED=true`를 넣고 Actions 수집을 끕니다.
- 적기 점수는 **하루 최저가**로 계산하므로 하루 4회로 충분하고 상대 사이트 부담도 줄입니다. 그 밖의 시각에는 Render도 깨우지 않습니다.
- 네이버 쇼핑 검색 API는 2026-07-31 종료되어(대체 API 없음) 관련 코드를 제거했습니다.

## 1. 수집 대상

| 쇼핑몰 | 판매처 주소 | robots.txt (2026-11 확인) | 읽는 값 |
|---|---|---|---|
| 다나와 | `https://prod.danawa.com/info/?pcode=<번호>` | 허용 (`/api/`, `/info/ajax/`, `/list/ajax/`는 금지 → 사용 안 함) | JSON-LD `AggregateOffer.lowPrice` |
| 에누리 | `https://www.enuri.com/detail.jsp?modelno=<번호>` | 허용 | JSON-LD `AggregateOffer.lowPrice` |

- 상품 목록: [`rpa/catalog.json`](../../rpa/catalog.json) — 실제 제품 400종(상한, 테스트로 검사). 기본 13종 + 인기 상품 `DANAWA-<pcode>`
  (세부 카테고리 15개: 노트북·모니터·무선이어폰·무선헤드폰·스마트폰·태블릿·그래픽카드·TV·공기청정기·무선청소기·에어프라이어·생수·롤화장지·기저귀·분유,
  각 다나와 목록 첫 페이지 인기순). 화면 대분류는 디지털·가전·생필품·패션·유아 5개를 그대로 씁니다.
- 쿠팡은 수집하지 않습니다: 봇 이름으로 접속하면 robots.txt부터 403(2026-11-10 재확인)이고 우회하지 않습니다.
  공식 경로인 쿠팡 파트너스 Open API는 파트너스 최종 승인(누적 판매 실적)이 있어야 키가 발급되고, 검색 API가 시간당 10회로 제한돼 가격 이력 수집에 맞지 않습니다.
  다나와는 모든 상품에 있고, 에누리는 같은 제품이 확인된 상품에만 연결합니다(약 90%).
- 에누리 대조(`collector.discover.match_enuri`): 에누리 검색(`price.enuri.com/search`, robots 허용·3초 간격) 상위 3개의 상세 페이지 JSON-LD에서
  ① 상품명이 옵션(SSD 용량·색상·스탠드 등)까지 같고 ② 제품 종류(사양 첫 항목)가 같으며 ③ 에누리 사양 항목의 80% 이상이 다나와 사양에도 있고
  ④ 그런 상품이 정확히 하나일 때만 연결합니다. 중고·해외구매·리퍼·렌탈 항목은 후보에서 빼고, 포장 수량만 다른 같은 제품은 순위가 가장 높은 1개만 남깁니다.
  `DANAWA-` model_no는 가격 이력이 이어지도록 그대로 둡니다(바꾸면 새 상품이 생김).
- `image_url`: 제조사 공식 사이트 상품 페이지에 모델명과 그 이미지가 함께 있는 것만 넣습니다(2026-11-10 확인, 43종 중 22종: 삼성·LG·로지텍·필립스·쿠쿠·알파스캔·크로스오버존·사운드코어·PALIT).
  인기 상품 중 LG전자 제품은 공식 상품 페이지(`lge.co.kr/product/<분류>/<모델명>`, 제목에 모델명이 있을 때만)의 대표 이미지를 씁니다.
  공식 이미지를 찾지 못한 상품(단종·robots 금지·접근 거부: 애플·소니·MSI·ZOTAC 등, 공식 페이지 없음)은 **다나와 상품 페이지의 대표 이미지**
  (`og:image`, `img.danuri.io`, 500px; 없으면 에누리 JSON-LD 이미지)를 씁니다. 2026-11-10 기준 400종 모두 이미지가 있고
  제조사 공식 74종(기존 22 + LG전자 52) · 다나와·에누리 326종입니다. 화면 사진 아래 출처를 "제조사 이미지" / "이미지: 다나와·에누리"로 구분해 표시합니다.
- `rpa/catalog.json` 자체 검증: `backend/tests/test_catalog.py::test_real_catalog_file_is_accepted`
  (API 형식 통과, 모든 상품 다나와 포함, 상품 400개 이하, 이미지 https).
- 부가 정보: 수집 때 JSON-LD의 판매처 수(`offerCount`)·최고가(`highPrice`)·평점·리뷰 수를 판매처별로, 다나와 사양 요약(`description`,
  `malls.json`의 `spec: true`)을 상품에 저장합니다 → 가격 비교 표와 상품 상세의 "주요 사양"에 표시. 추가 요청은 없습니다.
- 두 사이트는 **같은 회사(커넥트웨이브)** 가 운영해 최저가가 같은 경우가 많습니다. 판매처별 최저가는 각 사이트가 집계한 값입니다.
- 비교 사이트 최저가는 판매처마다 배송비 포함 여부가 달라 `shipping_fee=0`(사이트 표시 최저가)으로 저장합니다.
- 제외한 사이트와 이유: 11번가·SSG·롯데ON(robots.txt가 일반 봇 금지), G마켓(봇 이름으로 접속 시 403 → 거부로 보고 우회하지 않음),
  쿠팡(robots.txt 접근 403), 11번가 Open API(판매자 회원만 키 발급), 네이버쇼핑(API 종료·접속 차단).
- **이용 범위**: 다나와 약관은 회사 권리 정보를 사전 승낙 없이 영리 목적으로 이용하는 것을 금지합니다.
  이 프로젝트는 포트폴리오·비영리, 소수 상품, 하루 4회, 출처(판매처 이름·링크) 표시로 운영합니다. 상업 운영 전에는 제휴·허락을 받습니다.

### 상품 바꾸기·추가

1. 다나와·에누리에서 같은 제품의 상품 페이지 주소를 찾습니다(검색 페이지는 수집에 쓰지 않음. 다나와 검색은 Crawl-delay 10초).
2. `rpa/catalog.json`의 `products`에 `model_no`(영문·숫자·`-./+_`), 이름, 브랜드, 분류, 두 주소를 넣습니다.
3. main에 반영하면 다음 수집 때 `PUT /api/v1/rpa/catalog`가 상품·판매처를 만들거나 갱신합니다(여러 번 실행해도 결과가 같음).
   새 상품은 가격 이력 30일이 쌓이기 전까지 **판단 보류(HOLD)** 입니다.

### 시연용 상품(가상 12종)

`retire_mall_hosts`의 시연 쇼핑몰 3곳(`mall-a/b/c.example.com`)은 **삭제하지 않고 비활성화**합니다.
비활성 쇼핑몰의 판매처만 있는 상품은 검색·홈에서 빠지고 수집 대상에서도 빠집니다(가격 이력·관심 상품은 보존).
다시 보이게 하려면 해당 쇼핑몰을 `malls`에 넣거나 관리 SQL로 `malls.is_active`를 되돌립니다.
Netlify 데모 모드(브라우저 목업)는 영향이 없습니다.

## 2. 작업 4종

[`jobs.py`](../../rpa/collector/jobs.py)

| 작업 | 실행 시각(KST) | 하는 일 | 호출 API |
|---|---|---|---|
| `collect` | 00·06·12·18시 (Actions) | 카탈로그 동기화 → 수집 대상 목록 → 상품 페이지 수집 → 가격 없는 판매처는 실패 처리 → pandas 정제 → 일괄 저장 → 로그 | `PUT /rpa/catalog`, `GET /rpa/listings`, `POST /rpa/prices/bulk`, `POST /rpa/logs` |
| `train` | 매일 03:00 | 모델 재학습 요청(API가 백그라운드로 학습) | `POST /rpa/train` |
| `public` | 매일 06:00 | 한국소비자원 참가격 (`KCA_API_URL`, `DATA_GO_KR_KEY` 없으면 건너뜀, 아래 참가격 절) | `PUT /rpa/public-prices` |
| `report` | 매주 월 07:00 | 주간 가격 리포트(엑셀) → Actions 아티팩트(30일), EC2는 `~/timepick/reports/` | `GET /rpa/reports/weekly` |

### 참가격(`public`) — 2026-11-10 실제 응답으로 확인

- 서비스 주소 `KCA_API_URL=https://apis.data.go.kr/B551919/ProductPriceInfoService`, 응답은 XML(`<response><result><iros.openapi.service.vo.…VO>`).
  오퍼레이션 이름은 공공데이터포털 등록 그대로 `.do` 유무가 다릅니다: 가격 `getProductPriceInfoSvc`, 판매점 `getStoreInfoSvc.do`,
  기준 코드 `getStandardInfoSvc.do`, 상품 목록 `getProductInfoSvc.do`(604개). 잘못된 이름은 `NO_OPENAPI_SERVICE_ERROR`(HTTP 400).
- 가격 조회는 `goodInspectDay`(조사일, 금요일)와 `goodId`가 필요합니다. 조사는 격주 금요일, 공개는 약 1주 뒤라
  매일 최근 6주 금요일을 상품마다 조회하고(같은 날은 서버가 덮어씀), 같은 조사일의 판매점 가격 중 **최저가**와 그 판매점 업태(대형마트 등)를 저장합니다.
- [`rpa/public_price_map.json`](../../rpa/public_price_map.json): `goodId → {"model_no", "qty"}`. `qty`는 포장 수량 환산 배수입니다
  (참가격 `삼다수(2L*6개)` × 2 = 서비스 상품 `제주 삼다수 그린 2L × 12개`). 개수만 다른 같은 제품만 넣고, 용량·단계·길이가 다른 제품은 넣지 않습니다.
  현재 6종: 삼다수, 크리넥스 데코앤소프트·울트라클린 30m 30롤, 잘풀리는집 데코 30m 30롤, 모나리자 프레시티지 40m 30롤, 하기스 매직컴포트 팬티형 5단계(42매 × 2).
  화장지·하기스 5종은 참가격과 같은 제품을 다나와 검색(`search.danawa.com`, Crawl-delay 10초)으로 찾아 카탈로그에 추가했습니다.
- 상품 상세 화면에 가장 최근 조사일의 최저가를 "오프라인 최저가 (참가격)"로 판매점 업태·조사일과 함께 보여 줍니다(`GET /products/{id}`의 `offline_price`).
- 오류 문구의 요청 주소에 들어 있는 인증키는 `***`로 지운 뒤 수집 로그에 남깁니다. 공공데이터포털은 연결 시간 초과가 잦아 연결 오류만 3회 재시도합니다.

수동 실행: GitHub → Actions → **Collect (Render)** → Run workflow → 작업 선택. 로컬은 `cd rpa && python -m collector.jobs collect`
(`RPA_TARGET_API`를 로컬 API로 지정. 로컬 `.env`가 운영 TiDB를 가리키면 운영 데이터가 바뀝니다).

## 3. 수집 방식과 동적 페이지(Playwright)

| 규칙(`malls.json`) | 방식 | 사용처 |
|---|---|---|
| `"parser": "jsonld"` | Requests로 HTML을 받아 검색엔진용 구조화 데이터(schema.org Product)의 최저가를 읽음. 화면 디자인이 바뀌어도 잘 변하지 않음 | 다나와, 에누리 |
| `"parser": "css"`(기본) | `price`·`shipping`·`soldout` CSS 셀렉터 | 직접 판매 쇼핑몰을 추가할 때 |
| `"render": "playwright"` | Headless Chromium으로 JavaScript 실행 후의 화면을 읽음 | 가격을 화면에서 그리는 사이트(현재 없음) |

Playwright 실행기([`browser.py`](../../rpa/collector/browser.py))

- 수집 1회 동안 **브라우저 1개를 재사용**하고 탭은 매번 닫습니다. 필요한 규칙이 있을 때만 실행됩니다.
- 이미지·폰트·미디어, 다른 사이트(광고·분석)의 XHR, **robots.txt가 금지한 같은 사이트 XHR**(예: 다나와 `/info/ajax/`)은 보내지 않습니다.
- 컨테이너 공유 메모리 부족을 막는 `--disable-dev-shm-usage` 등으로 실행합니다.
- 설치: GitHub Actions는 `malls.json`에 `render: playwright` 규칙이 있을 때만 `python -m playwright install --with-deps chromium`(브라우저 캐시 사용).
  EC2 `rpa` 이미지에는 미리 설치되어 있습니다. Render 무료 Web Service(512MB, Cron 없음, 외부 요청 과다 시 정지 가능)에서는 돌리지 않습니다.

## 4. 수집 원칙 (변경 금지)

[`http.py`](../../rpa/collector/http.py)

- 사이트마다 `robots.txt`를 확인하고, 확인할 수 없으면 수집하지 않습니다.
- **같은 사이트끼리** 요청 간격 3초 이상, robots.txt에 `Crawl-delay`가 있으면 그 값을 따릅니다(다른 사이트끼리는 기다리지 않음).
- 봇 이름 `TimePickBot/1.0 (+contact: …)`를 그대로 밝힙니다. User-Agent 위장·IP 교체·CAPTCHA 풀이를 하지 않습니다.
- 401·403·404·410·429는 같은 실행에서 다시 요청하지 않고 실패로 기록합니다. 그 밖의 오류는 3회 재시도(3·6·12초).
- 가격을 읽지 못한 판매처(JSON-LD 없음: 차단 화면·구조 변경, 판매처 0곳)는 0원을 저장하지 않고 **실패**로 기록 → 관리자 수집 현황에 표시됩니다.
- 직전 가격 대비 ±50%를 넘는 값은 이상치로 제외합니다.

## 5. 설정 (환경 변수)

[`config.py`](../../rpa/collector/config.py)

| 변수 | 기본값 | GitHub Actions | EC2 |
|---|---|---|---|
| `RPA_TARGET_API` | http://localhost:8000 | Variable `RENDER_URL` | `http://api:8000`(compose 기본값, `.env`에 넣지 않음) |
| `RPA_API_KEY` | (없음 → 실행 거부) | Secret `RENDER_RPA_API_KEY` | api와 같은 값 |
| `COLLECT_ENABLED` | true | `true` | **`false`**(compose 기본값) |
| `SIMULATE_MALLS` | true | **`false`** | 수집하지 않으므로 무관 |
| `REQUEST_INTERVAL_SEC` | 3 | 기본값 | 기본값 |
| `COLLECT_MAX_PRODUCTS`, `COLLECT_ROTATE_REST` | 100, true | 기본값 | 수집하지 않으므로 무관 |
| `CATALOG`, `MALL_CONFIG` | `rpa/catalog.json`, `rpa/malls.json` | 기본값 | 기본값 |
| `KCA_API_URL`, `DATA_GO_KR_KEY` | (없음) | Variable / Secret (선택) | `.env` (선택) |

## 6. 인증

수집기는 모든 요청에 `X-RPA-KEY: <RPA_API_KEY>` 헤더를 붙이고([`api_client.py`](../../rpa/collector/api_client.py)),
API는 `hmac.compare_digest`로 비교합니다. 값이 다르면 401(`INVALID_RPA_KEY`)이 나며 수집 로그도 남지 않습니다.

## 7. 테스트

- `cd rpa && pytest -q`: JSON-LD 파서(정상·판매처 0곳·차단 화면·`@graph`), 사이트별 Crawl-delay, 카탈로그 동기화, 수집 끄기, Playwright 요청 차단 규칙 등
- `cd backend && pytest -q tests/test_catalog.py`: 카탈로그 생성·갱신·도메인 검증, 시연 쇼핑몰 비활성화 후 검색·수집 제외와 복구

다음 문서: [05. CI/CD 파이프라인](05-cicd.md)

## 8. 인기 상품 후보 찾기와 TiDB 무료 한도

- `python -m collector.discover`(Actions: 월요일 04시, 수동 `discover`): robots.txt가 허용하는 다나와 세부 카테고리 15개 목록 첫 페이지에서
  상위 40개씩(다음 페이지는 금지 경로 `/list/ajax/`라 쓰지 않음) 카탈로그에 없는 후보를 찾고 에누리를 자동 대조해 `reports/discovered.json`에 저장합니다.
  카탈로그 반영은 사람이 결과를 보고 합니다. 처음 전체 탐색은 약 1시간 30분(로컬 실행), 매주 실행은 새로 순위에 든 상품만 확인합니다.
- 단계별 수집: 매 구간(하루 4회) `priority` 상위 `COLLECT_MAX_PRODUCTS`(기본 100)개 + 나머지 상품 중 `product_id % 4 == 구간 번호`인 것
  (`COLLECT_ROTATE_REST`, 기본 true) → 모든 상품이 하루 한 번 이상 수집됩니다. 상품 400개 기준 1회 약 175개(판매처 약 340곳, 10~11분),
  하루 요청은 사이트당 약 700건입니다(전체를 하루 4회 수집하면 약 1,600건). 적기 점수는 하루 최저가로 계산하므로 하위 상품의 하루 1회 수집으로 판정이 달라지지 않습니다.
- 가격은 50곳씩 나눠 `POST /rpa/prices/bulk`로 보냅니다(서버가 상품마다 판정을 다시 계산하므로 요청 1회를 짧게 유지).
- `priority`: 인기 순위 기준 `(40 - 순위 + 1) × 10`. 기본 13종은 0이라 하루 1회 수집됩니다.
- TiDB Starter 무료: 인스턴스당 행 저장 5 GiB, 월 5,000만 RU. 프로젝트마다 인스턴스 1개를 쓰고, 연결은 `DB_POOL_SIZE`=3, `DB_MAX_OVERFLOW`=2.

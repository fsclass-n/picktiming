"""RPA 작업 (API 명세서 3.5)

  BOT-01 collect   카탈로그 동기화 → 다나와·에누리 상품 페이지 수집(JSON-LD) → pandas 정제 → 일괄 등록
                   실제 수집은 GitHub Actions(collect-render.yml, KST 0·6·12·18시)만 한다. EC2 rpa는 COLLECT_ENABLED=false
  BOT-02 public    매일 06:00  한국소비자원 참가격 공공데이터 수집
  BOT-03 train     매일 03:00  모델 재학습 요청(API 백그라운드 실행)
  BOT-04 report    매주 월 07:00 주간 가격 리포트(엑셀) 저장

실행: python -m collector.jobs collect|public|train|report
"""
import json
import logging
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from . import storage
from .api_client import ApiClient
from .config import Config
from .http import CollectError, PoliteSession
from .parsers import parse_jsonld_meta, parse_jsonld_offer, parse_product

log = logging.getLogger("collector")
OUTLIER_RATIO = 0.5  # 직전 가격 대비 ±50% 초과 변동은 이상치로 제외


def now(cfg: Config) -> datetime:
    return datetime.now(ZoneInfo(cfg.tz)).replace(tzinfo=None, microsecond=0)


def simulated_price(listing: dict, at: datetime) -> dict:
    """시연용 쇼핑몰(*.example.com): 직전 가격 기준 ±1.5% 무작위 변동"""
    rnd = random.Random(f"{listing['listing_id']}-{at:%Y%m%d%H}")
    last = listing.get("last_price") or 10000
    price = int(round(last * (1 + rnd.uniform(-0.015, 0.015)) / 10) * 10)
    return {"price": price, "shipping_fee": listing.get("last_shipping_fee") or 0, "in_stock": rnd.random() > 0.02}


def clean(rows: list[dict], listings: dict[int, dict]) -> pd.DataFrame:
    """pandas 정제: 품절·0원 제외 표시, 이상치 제거, 중복 제거"""
    df = pd.DataFrame(rows, columns=["listing_id", "price", "shipping_fee", "in_stock"])
    if df.empty:
        return df
    df = df.drop_duplicates("listing_id", keep="last")
    last = df["listing_id"].map(lambda i: listings[i].get("last_price"))
    ratio = (df["price"] / last).where(last.notna() & (last > 0))
    outlier = df["in_stock"] & ratio.notna() & ((ratio < 1 - OUTLIER_RATIO) | (ratio > 1 + OUTLIER_RATIO))
    if outlier.any():
        log.warning("이상치 제외 %d건: %s", int(outlier.sum()), df.loc[outlier, "listing_id"].tolist())
    return df[~outlier].astype({"listing_id": int, "price": int, "shipping_fee": int, "in_stock": bool})


SLOT_HOURS = 6  # 하루 4회: 00·06·12·18시에 시작하는 구간


def slot_start(at: datetime) -> datetime:
    return at.replace(hour=at.hour - at.hour % SLOT_HOURS, minute=0, second=0, microsecond=0)


SLOTS_PER_DAY = 24 // SLOT_HOURS
POST_CHUNK = 50  # 가격 일괄 등록 1회 판매처 수(서버가 상품마다 판정을 다시 계산하므로 Render 무료 플랜 요청 시간을 짧게 유지)


def limit_products(items: list[dict], limit: int, slot: int | None = None) -> list[dict]:
    """서버가 우선순위 높은 순으로 준 판매처 목록에서 상품 기준 상위 limit개는 매회 수집한다.

    slot(이번 6시간 구간 번호 0~3)을 주면 나머지 상품도 product_id % 4 == slot인 것을 함께 수집한다 → 하루 한 번씩 돌아가며 전부 수집.
    적기 점수는 하루 최저가로 계산하므로 하위 상품은 하루 1회로 충분하고, 상대 사이트 요청은 전체 4회 대비 절반 이하로 줄어든다.
    """
    key = lambda l: l.get("product_id", ("listing", l["listing_id"]))  # noqa: E731
    top = set(list(dict.fromkeys(key(l) for l in items))[:limit])
    rotated = lambda k: slot is not None and isinstance(k, int) and k % SLOTS_PER_DAY == slot  # noqa: E731
    return [l for l in items if key(l) in top or rotated(key(l))]


def scrape(session: PoliteSession, url: str, rule: dict) -> dict:
    """규칙(malls.json)대로 한 판매처의 가격을 읽는다. render=playwright면 브라우저로 화면을 그린 뒤 읽는다"""
    soup = session.fetch(url, render=rule.get("render") == "playwright", wait_for=rule.get("wait_for") or rule.get("price"))
    if rule.get("parser") == "jsonld":  # 판매처 수·최고가·평점도 함께 읽는다(spec=true인 쇼핑몰만 사양 요약)
        return {**parse_jsonld_offer(soup), **parse_jsonld_meta(soup, spec=bool(rule.get("spec")))}
    return parse_product(soup, rule)


META_KEYS = ("spec", "offer_count", "high_price", "rating", "review_count")


def collect(cfg: Config, api: ApiClient) -> dict:
    if not cfg.collect_enabled:
        return {"status": "SKIPPED", "reason": "COLLECT_ENABLED=false"}
    started = now(cfg)
    if cfg.collect_if_due and hasattr(api, "status"):
        last = api.status().get("last_collect_at")
        if last and datetime.fromisoformat(last) >= slot_start(started):
            return {"status": "SKIPPED", "reason": f"이번 구간({slot_start(started):%H}시~) 수집 완료: {last}"}
    catalog = cfg.catalog()
    if catalog and hasattr(api, "sync_catalog"):
        log.info("카탈로그 동기화: %s", api.sync_catalog(catalog))  # 수집 대상 상품·판매처를 DB에 맞춤(여러 번 호출해도 같음)
    slot = slot_start(started).hour // SLOT_HOURS if cfg.rotate_rest else None
    listings = {l["listing_id"]: l for l in limit_products(api.listings(), cfg.max_products, slot)}
    rules = cfg.mall_rules()
    rows, failed, skipped, errors = [], 0, 0, []
    with PoliteSession(cfg.user_agent, cfg.request_interval_sec) as session:
        for l in listings.values():
            host = urlparse(l["url"]).netloc
            try:
                if host.endswith(".example.com"):
                    if not cfg.simulate:
                        skipped += 1
                        continue
                    rows.append({"listing_id": l["listing_id"], **simulated_price(l, started)})
                elif l["mall"] in rules:
                    rows.append({"listing_id": l["listing_id"], **scrape(session, l["url"], rules[l["mall"]])})
                else:
                    skipped += 1  # 규칙이 없는(수집을 허용받지 않은) 쇼핑몰은 수집하지 않음
            except (CollectError, requests.RequestException) as exc:
                failed += 1
                errors.append(str(exc))
    # 가격을 읽지 못한 판매처(0원: 판매처 0곳·구조 변경·차단 화면)는 저장하지 않고 실패로 기록한다 → 관리자 수집 현황에 표시
    missing = [r["listing_id"] for r in rows if r["price"] <= 0]
    if missing:
        failed += len(missing)
        errors.append(f"가격을 읽지 못한 판매처 {len(missing)}곳(구조 변경·차단 확인 필요): {missing[:10]}")
        log.warning(errors[-1])
        rows = [r for r in rows if r["price"] > 0]
    meta = {r["listing_id"]: {k: r[k] for k in META_KEYS if k in r} for r in rows}  # 가격 정제(pandas)와 따로 두었다가 다시 붙인다
    df = clean(rows, listings)
    if len(df):
        storage.upload(cfg.s3_bucket, f"{cfg.s3_prefix}/raw/{started:%Y/%m/%d/%H%M}.json", df.to_json(orient="records", force_ascii=False).encode(),
                       "application/json", cfg.aws_region)
    records = [{**r, **meta.get(r["listing_id"], {})} for r in df.to_dict("records")]
    result: dict = {"inserted": 0}
    for n in range(0, len(records), POST_CHUNK):
        for k, v in api.post_prices(records[n:n + POST_CHUNK], started).items():
            result[k] = result.get(k, 0) + v if isinstance(v, int) else v
    status = "SUCCESS" if failed == 0 else ("PARTIAL" if len(df) else "FAIL")
    msg = f"수집 {len(df)}건, 실패 {failed}건, 건너뜀 {skipped}건" + (f" / {errors[0]}" if errors else "")
    api.log("collect_prices", status, started, now(cfg), collected=int(result.get("inserted", 0)), failed=failed, message=msg)
    return {"status": status, **result, "failed": failed, "skipped": skipped}


# 한국소비자원 참가격(공공데이터포털 B551919/ProductPriceInfoService, XML). 2026-11-10 실제 호출로 확인한 오퍼레이션 이름(.do 유무가 서로 다르다)
KCA_PRICE_OP = "getProductPriceInfoSvc"   # 가격: goodInspectDay(조사일, 금요일) + goodId 필수
KCA_STORE_OP = "getStoreInfoSvc.do"       # 판매점: entpId → entpTypeCode(업태)
KCA_CODE_OP = "getStandardInfoSvc.do"     # 기준 코드: classCode=BU → 업태 이름(대형마트·편의점 등)
SURVEY_WEEKS = 6  # 조사는 격주 금요일, 공개는 약 1주 뒤 → 최근 6주 금요일을 다시 조회한다(같은 날은 서버가 덮어씀)


def survey_days(today: date, weeks: int = SURVEY_WEEKS) -> list[str]:
    """오늘 이전 가장 가까운 금요일부터 weeks주 전까지의 조사일(YYYYMMDD, 최신순)"""
    friday = today - timedelta(days=(today.weekday() - 4) % 7)
    return [f"{friday - timedelta(weeks=i):%Y%m%d}" for i in range(weeks)]


def kca_records(payload: str) -> list[dict]:
    """참가격 XML의 <result> 아래 레코드(iros.openapi.service.vo.goodPriceVO 등) → dict 목록. 포털·API 오류 응답은 ValueError"""
    root = ET.fromstring(payload)
    if root.tag == "OpenAPI_ServiceResponse":
        raise ValueError(f"공공데이터포털 오류: {root.findtext('.//errMsg')} {root.findtext('.//returnAuthMsg') or ''}".strip())
    if (code := root.findtext("resultCode")) not in (None, "00"):
        raise ValueError(f"참가격 API 오류 {code}: {root.findtext('resultMsg')}")
    result = root.find("result")
    return [{c.tag: (c.text or "").strip() for c in rec} for rec in (result if result is not None else [])]


def public_targets(mapping: dict) -> dict[str, tuple[str, float]]:
    """public_price_map.json → {goodId: (model_no, qty)}. 값은 model_no 문자열 또는 {"model_no", "qty"}(참가격 가격 × qty = 우리 상품 1개)"""
    out: dict[str, tuple[str, float]] = {}
    for good_id, v in mapping.items():
        if isinstance(v, str) and not good_id.startswith("_"):
            out[good_id] = (v, 1.0)
        elif isinstance(v, dict) and v.get("model_no"):
            out[good_id] = (v["model_no"], float(v.get("qty", 1)))
    return out


def parse_public(payload: str, mapping: dict, stores: dict[str, str] | None = None) -> list[dict]:
    """참가격 가격 응답 → 상품·조사일별 최저가 [{model_no, good_id, price, store_type, survey_date}]

    같은 날 여러 판매점 가격 중 최저가(온라인 최저가와 같은 기준)를 qty배로 환산하고, 그 판매점의 업태를 store_type으로 남긴다.
    """
    targets, best = public_targets(mapping), {}
    for r in kca_records(payload):
        good_id, day, price = r.get("goodId", ""), r.get("goodInspectDay", "")[:8], int(float(r.get("goodPrice") or 0))
        if good_id in targets and price > 0 and len(day) == 8 and ((good_id, day) not in best or price < best[(good_id, day)][0]):
            best[(good_id, day)] = (price, r.get("entpId"))
    return [{"model_no": targets[g][0], "good_id": g, "price": round(p * targets[g][1]), "store_type": (stores or {}).get(e),
             "survey_date": f"{d[:4]}-{d[4:6]}-{d[6:]}"} for (g, d), (p, e) in sorted(best.items())]


def hide_key(cfg: Config, exc: Exception) -> str:
    """오류 문구(요청 주소 포함)에서 인증키를 지운다 — 수집 로그·Actions 로그에 키가 남지 않게"""
    msg = str(exc)
    for k in {cfg.public_api_key, quote(cfg.public_api_key, safe="")} - {""}:
        msg = msg.replace(k, "***")
    return msg[:500]


def kca_fetch(cfg: Config):
    """참가격 오퍼레이션 호출 함수. KCA_API_URL은 서비스 주소(…/ProductPriceInfoService), 오퍼레이션까지 넣어도 동작한다"""
    base = re.sub(r"/get\w+(\.do)?$", "", cfg.public_api_url.rstrip("/"))

    def fetch(op: str, **params) -> str:
        for attempt in range(3):  # 공공데이터포털은 연결 시간 초과가 잦다 → 연결 오류만 재시도
            try:
                r = requests.get(f"{base}/{op}", params={"serviceKey": cfg.public_api_key, **params}, timeout=(15, 120))
                break
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(5 * 2 ** attempt)
        if r.status_code >= 400 and "OpenAPI_ServiceResponse" in r.text:
            kca_records(r.text)  # 포털 오류 응답이면 이유(인증키 미등록·서비스 없음 등)가 담긴 ValueError
        r.raise_for_status()
        return r.text

    return fetch


def kca_store_types(fetch) -> dict[str, str]:
    """판매점 아이디 → 업태 이름(대형마트·편의점 등)"""
    names = {r.get("code"): r.get("codeName") for r in kca_records(fetch(KCA_CODE_OP, classCode="BU"))}
    return {r["entpId"]: names.get(r.get("entpTypeCode")) or r.get("entpTypeCode") for r in kca_records(fetch(KCA_STORE_OP)) if r.get("entpId")}


def collect_public(cfg: Config, api: ApiClient, fetch=None) -> dict:
    started = now(cfg)
    if not (cfg.public_api_url and cfg.public_api_key):
        api.log("collect_public_prices", "PARTIAL", started, now(cfg), message="KCA_API_URL / DATA_GO_KR_KEY 미설정으로 건너뜀")
        return {"status": "SKIPPED"}
    mapping = json.loads(cfg.public_map_path.read_text(encoding="utf-8")) if cfg.public_map_path.exists() else {}
    if not (targets := public_targets(mapping)):
        api.log("collect_public_prices", "PARTIAL", started, now(cfg), message="public_price_map.json에 매핑된 상품이 없어 건너뜀")
        return {"status": "SKIPPED"}
    fetch = fetch or kca_fetch(cfg)
    try:
        payloads = [fetch(KCA_PRICE_OP, goodInspectDay=d, goodId=g) for g in targets for d in survey_days(started.date())]
        stores: dict[str, str] = {}
        if any("<goodPrice>" in p for p in payloads):
            try:
                stores = kca_store_types(fetch)
            except (requests.RequestException, ET.ParseError, ValueError) as exc:  # 업태는 부가 정보라 실패해도 가격은 저장
                log.warning("참가격 판매점 업태 조회 실패: %s", hide_key(cfg, exc))
        items = [i for p in payloads for i in parse_public(p, mapping, stores)]
        res = api.put_public_prices(items) if items else {"saved": 0}
        api.log("collect_public_prices", "SUCCESS", started, now(cfg), collected=res.get("saved", 0),
                message=f"참가격 데이터 갱신: 상품 {len(targets)}개 × 최근 {SURVEY_WEEKS}주 조사일, 저장 {res.get('saved', 0)}건")
        return {"status": "SUCCESS", **res}
    except (requests.RequestException, ET.ParseError, ValueError) as exc:
        msg = hide_key(cfg, exc)
        api.log("collect_public_prices", "FAIL", started, now(cfg), failed=1, message=msg)
        return {"status": "FAIL", "error": msg}


def train(cfg: Config, api: ApiClient) -> dict:
    return api.train()


def report(cfg: Config, api: ApiClient) -> dict:
    data, name = api.weekly_report()
    cfg.report_dir.mkdir(parents=True, exist_ok=True)
    (cfg.report_dir / name).write_bytes(data)
    s3 = storage.upload(cfg.s3_bucket, f"{cfg.s3_prefix}/reports/{name}", data,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", cfg.aws_region)
    api.log("weekly_report", "SUCCESS", now(cfg), now(cfg), collected=1, message=f"{name} 저장" + (f" · {s3}" if s3 else ""))
    return {"status": "SUCCESS", "file": str(cfg.report_dir / name), "s3": s3}


JOBS = {"collect": collect, "public": collect_public, "train": train, "report": report}


def run(name: str, cfg: Config | None = None) -> dict:
    cfg = cfg or Config()
    if not cfg.rpa_api_key:
        raise SystemExit("RPA_API_KEY 환경 변수가 필요합니다.")
    return JOBS[name](cfg, ApiClient(cfg.api_base_url, cfg.rpa_api_key))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        raise SystemExit(f"사용법: python -m collector.jobs {{{'|'.join(JOBS)}}}")
    print(run(sys.argv[1]))

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
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from . import storage
from .api_client import ApiClient
from .config import Config
from .http import CollectError, PoliteSession
from .parsers import parse_jsonld_offer, parse_product

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


def scrape(session: PoliteSession, url: str, rule: dict) -> dict:
    """규칙(malls.json)대로 한 판매처의 가격을 읽는다. render=playwright면 브라우저로 화면을 그린 뒤 읽는다"""
    soup = session.fetch(url, render=rule.get("render") == "playwright", wait_for=rule.get("wait_for") or rule.get("price"))
    return parse_jsonld_offer(soup) if rule.get("parser") == "jsonld" else parse_product(soup, rule)


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
    listings = {l["listing_id"]: l for l in api.listings()}
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
    df = clean(rows, listings)
    if len(df):
        storage.upload(cfg.s3_bucket, f"{cfg.s3_prefix}/raw/{started:%Y/%m/%d/%H%M}.json", df.to_json(orient="records", force_ascii=False).encode(),
                       "application/json", cfg.aws_region)
    result = api.post_prices(df.to_dict("records"), started) if len(df) else {"inserted": 0}
    status = "SUCCESS" if failed == 0 else ("PARTIAL" if len(df) else "FAIL")
    msg = f"수집 {len(df)}건, 실패 {failed}건, 건너뜀 {skipped}건" + (f" / {errors[0]}" if errors else "")
    api.log("collect_prices", status, started, now(cfg), collected=int(result.get("inserted", 0)), failed=failed, message=msg)
    return {"status": status, **result, "failed": failed, "skipped": skipped}


def parse_public(payload: str, mapping: dict) -> list[dict]:
    """참가격 응답(JSON 또는 XML) → [{model_no, good_id, price, survey_date}]. 필드명은 공공데이터포털 명세에 맞게 mapping으로 지정"""
    f = mapping.get("_fields", {"good_id": "goodId", "price": "goodPrice", "date": "goodInspectDay", "store": "entpName"})
    items: list[dict] = []
    try:
        data = json.loads(payload)
        found = data.get("response", {}).get("body", {}).get("items", data.get("items", []))
        records = found.get("item", found) if isinstance(found, dict) else found
    except json.JSONDecodeError:
        records = [{c.tag: (c.text or "").strip() for c in it} for it in ET.fromstring(payload).iter("item")]
    for r in records if isinstance(records, list) else [records]:
        good_id = str(r.get(f["good_id"], ""))
        model_no = mapping.get(good_id)
        if not model_no:
            continue
        day = str(r.get(f["date"], ""))[:8]
        items.append({"model_no": model_no, "good_id": good_id, "price": int(float(r.get(f["price"], 0))),
                      "store_type": r.get(f["store"]), "survey_date": f"{day[:4]}-{day[4:6]}-{day[6:8]}"})
    return items


def collect_public(cfg: Config, api: ApiClient) -> dict:
    started = now(cfg)
    if not (cfg.public_api_url and cfg.public_api_key):
        api.log("collect_public_prices", "PARTIAL", started, now(cfg), message="KCA_API_URL / DATA_GO_KR_KEY 미설정으로 건너뜀")
        return {"status": "SKIPPED"}
    mapping = json.loads(cfg.public_map_path.read_text(encoding="utf-8")) if cfg.public_map_path.exists() else {}
    try:
        r = requests.get(cfg.public_api_url, params={"serviceKey": cfg.public_api_key}, timeout=30)
        r.raise_for_status()
        items = parse_public(r.text, mapping)
        res = api.put_public_prices(items) if items else {"saved": 0}
        api.log("collect_public_prices", "SUCCESS", started, now(cfg), collected=res.get("saved", 0), message="참가격 데이터 갱신")
        return {"status": "SUCCESS", **res}
    except (requests.RequestException, ET.ParseError, ValueError) as exc:
        api.log("collect_public_prices", "FAIL", started, now(cfg), failed=1, message=str(exc))
        return {"status": "FAIL", "error": str(exc)}


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

"""상품 페이지 파싱 (쇼핑몰별 규칙은 malls.json으로 분리)

  parser "css"(기본) : CSS 셀렉터로 가격·배송비·품절 표시를 읽는다
  parser "jsonld"    : 검색엔진용 구조화 데이터(schema.org Product → Offer/AggregateOffer)를 읽는다 — 다나와·에누리
                       화면 디자인이 바뀌어도 잘 변하지 않아 셀렉터보다 안정적이다
"""
import json
import re

from bs4 import BeautifulSoup

UNAVAILABLE = {"price": 0, "shipping_fee": 0, "in_stock": False}


def parse_price(text: str | None) -> int | None:
    """'129,000원', '12.9만원', '무료', '3,000원~' 등 → 정수(원). 무료는 0"""
    if text is None:
        return None
    t = text.replace(",", "").replace(" ", "")
    if "무료" in t or t.lower() in {"free", "0"}:
        return 0
    if m := re.search(r"(\d+(?:\.\d+)?)만", t):
        return int(round(float(m.group(1)) * 10_000))
    m = re.search(r"(\d{2,})", t)
    return int(m.group(1)) if m else None


def parse_product(soup: BeautifulSoup, rule: dict) -> dict:
    """rule: {"price": "css", "shipping": "css"(선택), "soldout": "css"(선택)}"""
    price_el = soup.select_one(rule["price"])
    price = parse_price(price_el.get_text(strip=True) if price_el else None)
    ship_el = soup.select_one(rule["shipping"]) if rule.get("shipping") else None
    shipping = parse_price(ship_el.get_text(strip=True)) if ship_el else 0
    sold_out = bool(rule.get("soldout") and soup.select_one(rule["soldout"]))
    if price is None or price <= 0:
        sold_out = True  # 가격이 없거나 0원이면 품절로 처리 (BUG-04)
    return {"price": price or 0, "shipping_fee": shipping or 0, "in_stock": not sold_out}


def jsonld_items(soup: BeautifulSoup):
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict):
                yield from (g for g in item.get("@graph", []) if isinstance(g, dict))
                yield item


def _int(value) -> int | None:
    try:
        n = int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None
    return n if n >= 0 else None


def parse_jsonld_meta(soup: BeautifulSoup, spec: bool = False) -> dict:
    """가격 비교 상품 페이지의 부가 정보(값이 있는 것만): 판매처 수·최고가·평점(5점 환산)·리뷰 수, spec=True면 사양 요약(description)"""
    item = next((i for i in jsonld_items(soup) if i.get("@type") == "Product"), None)
    if item is None:
        return {}
    offer = item.get("offers") or {}
    offer = (offer[0] if offer else {}) if isinstance(offer, list) else offer
    rating = item.get("aggregateRating") or {}
    out = {"offer_count": _int(offer.get("offerCount")), "high_price": _int(offer.get("highPrice")), "review_count": _int(rating.get("reviewCount"))}
    try:
        value, best = float(rating.get("ratingValue")), float(rating.get("bestRating") or 5)
        out["rating"] = round(min(5.0, max(0.0, value / best * 5)), 2) if best > 0 else None
    except (TypeError, ValueError):
        out["rating"] = None
    if spec and (text := " ".join(str(item.get("description") or "").split())):
        out["spec"] = text[:500]
    return {k: v for k, v in out.items() if v is not None}


def parse_jsonld_offer(soup: BeautifulSoup) -> dict:
    """가격 비교 상품 페이지의 최저가(AggregateOffer.lowPrice, 단일 Offer는 price).

    비교 사이트 최저가는 판매처마다 배송비 포함 여부가 달라 shipping_fee=0으로 저장한다(사이트 표시 최저가 기준).
    판매처 0곳·가격 없음·JSON-LD 없음(차단 화면, 구조 변경)은 품절로 처리해 0원이 저장되지 않게 한다.
    """
    for item in jsonld_items(soup):
        if item.get("@type") != "Product":
            continue
        offer = item.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        if str(offer.get("offerCount", "1")).strip() in {"0", ""}:
            return dict(UNAVAILABLE)
        price = parse_price(str(offer.get("lowPrice") or offer.get("price") or ""))
        if price and price > 0:
            return {"price": price, "shipping_fee": 0, "in_stock": True}
    return dict(UNAVAILABLE)

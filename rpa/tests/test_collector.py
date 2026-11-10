from datetime import datetime

from bs4 import BeautifulSoup

from collector import jobs
from collector.config import Config
from collector.parsers import parse_price, parse_product
from collector.scheduler import due_jobs

HTML = """<div class="product-price"><span class="sale">129,000원</span></div><span class="delivery-fee">3,000원</span>"""
RULE = {"price": ".product-price .sale", "shipping": ".delivery-fee", "soldout": ".btn-soldout"}


def test_parse_price_formats():
    assert parse_price("1,290,000원~") == 1290000
    assert parse_price("12.9만원") == 129000
    assert parse_price("무료배송") == 0
    assert parse_price("") is None and parse_price(None) is None


def test_parse_product_and_soldout():
    assert parse_product(BeautifulSoup(HTML, "html.parser"), RULE) == {"price": 129000, "shipping_fee": 3000, "in_stock": True}
    sold = BeautifulSoup(HTML + '<button class="btn-soldout">품절</button>', "html.parser")
    assert parse_product(sold, RULE)["in_stock"] is False
    zero = BeautifulSoup('<div class="product-price"><span class="sale">0원</span></div>', "html.parser")
    assert parse_product(zero, RULE)["in_stock"] is False  # 0원 수집 방지


def test_clean_removes_outliers_and_duplicates():
    listings = {1: {"last_price": 100000}, 2: {"last_price": 100000}, 3: {"last_price": None}}
    rows = [{"listing_id": 1, "price": 99000, "shipping_fee": 0, "in_stock": True},
            {"listing_id": 1, "price": 98000, "shipping_fee": 0, "in_stock": True},
            {"listing_id": 2, "price": 10000, "shipping_fee": 0, "in_stock": True},
            {"listing_id": 3, "price": 5000, "shipping_fee": 0, "in_stock": True}]
    df = jobs.clean(rows, listings)
    assert sorted(df["listing_id"]) == [1, 3] and int(df.loc[df.listing_id == 1, "price"].iloc[0]) == 98000


def test_simulated_price_is_deterministic():
    l = {"listing_id": 5, "last_price": 100000, "last_shipping_fee": 3000}
    t = datetime(2026, 12, 1, 10)
    a, b = jobs.simulated_price(l, t), jobs.simulated_price(l, t)
    assert a == b and 98000 <= a["price"] <= 102000 and a["shipping_fee"] == 3000


def test_due_jobs():
    assert due_jobs(datetime(2026, 12, 7, 7, 0)) == ["collect", "report"]  # 월요일 07:00
    assert due_jobs(datetime(2026, 12, 8, 3, 0)) == ["collect", "train"]
    assert due_jobs(datetime(2026, 12, 8, 6, 0)) == ["collect", "public"]
    assert due_jobs(datetime(2026, 12, 8, 6, 30)) == []


def test_parse_public_json_and_xml():
    mapping = {"G1": "W2L12"}
    js = '{"response": {"body": {"items": {"item": [{"goodId": "G1", "goodPrice": "8800", "goodInspectDay": "20261020"}]}}}}'
    assert jobs.parse_public(js, mapping) == [{"model_no": "W2L12", "good_id": "G1", "price": 8800, "store_type": None,
                                               "survey_date": "2026-10-20"}]
    xml = "<response><body><items><item><goodId>G1</goodId><goodPrice>8700</goodPrice><goodInspectDay>20261021</goodInspectDay></item></items></body></response>"
    assert jobs.parse_public(xml, mapping)[0]["price"] == 8700


class FakeApi:
    def __init__(self, listings):
        self._l, self.posted, self.logs = listings, None, []

    def listings(self):
        return self._l

    def post_prices(self, items, at):
        self.posted = items
        return {"inserted": len(items)}

    def log(self, *a, **kw):
        self.logs.append((a, kw))


def test_collect_simulated_and_skips_unconfigured(monkeypatch):
    monkeypatch.setenv("SIMULATE_MALLS", "true")
    api = FakeApi([{"listing_id": 1, "mall": "쇼핑몰 A", "url": "https://mall-a.example.com/p/1", "last_price": 10000, "last_shipping_fee": 0},
                   {"listing_id": 2, "mall": "미등록몰", "url": "https://real-shop.test/p/2", "last_price": 10000, "last_shipping_fee": 0}])
    res = jobs.collect(Config(), api)
    assert res["inserted"] == 1 and res["skipped"] == 1 and api.posted[0]["listing_id"] == 1
    assert api.logs[0][0][0] == "collect_prices"


def test_s3_upload_is_skipped_without_bucket():
    from collector import storage

    assert storage.upload("", "k", b"x", "text/plain") is None


# ---------------------------------------------------------------- 실제 수집(다나와·에누리 상품 페이지의 JSON-LD)
def _jsonld(offers: dict, kind: str = "Product") -> str:
    import json

    return (f'<html><head><script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@type": kind, "name": "X", "offers": offers})}'
            '</script></head><body>화면 문구 123,000원</body></html>')


def test_parse_jsonld_aggregate_offer_lowest_price():
    from collector.parsers import parse_jsonld_offer

    danawa = _jsonld({"@type": "AggregateOffer", "lowPrice": "315000", "offerCount": "116", "priceCurrency": "KRW"})
    assert parse_jsonld_offer(BeautifulSoup(danawa, "html.parser")) == {"price": 315000, "shipping_fee": 0, "in_stock": True}
    enuri = _jsonld({"@type": "AggregateOffer", "lowPrice": 226510, "highPrice": 517000, "offerCount": 222})
    assert parse_jsonld_offer(BeautifulSoup(enuri, "html.parser"))["price"] == 226510
    single = _jsonld({"@type": "Offer", "price": "8,900"})
    assert parse_jsonld_offer(BeautifulSoup(single, "html.parser"))["price"] == 8900


def test_parse_jsonld_marks_missing_or_empty_offers_as_unavailable():
    from collector.parsers import parse_jsonld_offer

    for html in (_jsonld({"@type": "AggregateOffer", "lowPrice": "315000", "offerCount": 0}),  # 판매처 0곳
                 _jsonld({"@type": "AggregateOffer"}),  # 가격 없음
                 _jsonld({"lowPrice": "1000"}, kind="BreadcrumbList"),  # Product가 아님
                 '<script type="application/ld+json">{깨진 JSON</script>',
                 "<html>JSON-LD 없음(차단 화면·구조 변경)</html>"):
        assert parse_jsonld_offer(BeautifulSoup(html, "html.parser")) == {"price": 0, "shipping_fee": 0, "in_stock": False}
    graph = '<script type="application/ld+json">{"@graph": [{"@type": "Product", "offers": {"lowPrice": 5000}}]}</script>'
    assert parse_jsonld_offer(BeautifulSoup(graph, "html.parser"))["price"] == 5000


def test_robots_crawl_delay_is_respected_per_host():
    from collector.http import PoliteSession

    s = PoliteSession("TimePickBot/1.0", interval_sec=3)
    for root, lines in {"https://search.example.org": ["User-agent: *", "Crawl-delay: 10"], "https://prod.example.org": ["User-agent: *", "Allow: /"]}.items():
        import urllib.robotparser

        rp = urllib.robotparser.RobotFileParser()
        rp.parse(lines)
        s._robots[root] = rp
    assert s.delay_for("https://search.example.org/q") == 10
    assert s.delay_for("https://prod.example.org/p") == 3


def test_requests_to_different_hosts_do_not_wait_for_each_other(monkeypatch):
    from collector import http

    slept = []
    monkeypatch.setattr(http.time, "sleep", slept.append)
    s = http.PoliteSession("TimePickBot/1.0", interval_sec=3)
    s.wait("https://a.example.org/1")
    s.wait("https://b.example.org/1")
    assert slept == []  # 다른 사이트는 바로 요청
    s.wait("https://a.example.org/2")
    assert len(slept) == 1 and 2.5 < slept[0] <= 3  # 같은 사이트는 간격 유지


class CatalogApi(FakeApi):
    def __init__(self, listings):
        super().__init__(listings)
        self.catalog = None

    def sync_catalog(self, body):
        self.catalog = body
        return {"products_created": 0}


def test_collect_syncs_catalog_and_parses_jsonld(monkeypatch, tmp_path):
    import json

    from collector import http

    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"_comment": "설명", "malls": [{"name": "다나와", "base_url": "https://prod.danawa.com"}],
                                   "products": [], "retire_mall_hosts": ["mall-a.example.com"]}, ensure_ascii=False), encoding="utf-8")
    rules = tmp_path / "malls.json"
    rules.write_text(json.dumps({"다나와": {"parser": "jsonld"}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CATALOG", str(catalog))
    monkeypatch.setenv("MALL_CONFIG", str(rules))
    monkeypatch.setenv("SIMULATE_MALLS", "false")
    page = _jsonld({"@type": "AggregateOffer", "lowPrice": "315000", "offerCount": "116"})
    monkeypatch.setattr(http.PoliteSession, "fetch", lambda self, url, render=False, wait_for=None: BeautifulSoup(page, "html.parser"))
    api = CatalogApi([{"listing_id": 7, "mall": "다나와", "url": "https://prod.danawa.com/info/?pcode=28208783", "last_price": 316000, "last_shipping_fee": 0},
                      {"listing_id": 8, "mall": "쇼핑몰 A", "url": "https://mall-a.example.com/p/1", "last_price": 10000, "last_shipping_fee": 0}])
    res = jobs.collect(Config(), api)
    assert "_comment" not in api.catalog and api.catalog["retire_mall_hosts"] == ["mall-a.example.com"]
    assert api.posted == [{"listing_id": 7, "price": 315000, "shipping_fee": 0, "in_stock": True}]
    assert res["skipped"] == 1  # 모의 가격 꺼짐 → 시연 쇼핑몰 건너뜀


def test_collect_disabled_environment_does_nothing(monkeypatch):
    """EC2 rpa 컨테이너(COLLECT_ENABLED=false): 외부 사이트 수집은 GitHub Actions만 한다"""
    monkeypatch.setenv("COLLECT_ENABLED", "false")
    api = FakeApi([{"listing_id": 1, "mall": "쇼핑몰 A", "url": "https://mall-a.example.com/p/1", "last_price": 1, "last_shipping_fee": 0}])
    assert jobs.collect(Config(), api) == {"status": "SKIPPED", "reason": "COLLECT_ENABLED=false"}
    assert api.posted is None and api.logs == []
    assert due_jobs(datetime(2026, 12, 8, 3, 0), collect=False) == ["train"]


class FakeRoute:
    def __init__(self, url, kind):
        self.request = type("Req", (), {"url": url, "resource_type": kind})()
        self.result = None

    def abort(self):
        self.result = "abort"

    def continue_(self):
        self.result = "continue"


def test_browser_blocks_heavy_and_disallowed_requests():
    """Playwright 렌더링: 이미지·폰트·미디어, 다른 사이트의 XHR, robots.txt 금지 경로(예: 다나와 /info/ajax/) 호출을 보내지 않는다"""
    from collector.browser import BrowserSession

    b = BrowserSession("TimePickBot/1.0", allowed=lambda url: "/info/ajax/" not in url)
    b._page_host = "prod.danawa.com"
    cases = {("https://img.danawa.com/a.jpg", "image"): "abort", ("https://prod.danawa.com/font.woff2", "font"): "abort",
             ("https://prod.danawa.com/info/ajax/getPrice.php", "xhr"): "abort", ("https://ads.example.net/track", "fetch"): "abort",
             ("https://prod.danawa.com/info/price.json", "fetch"): "continue", ("https://static.danawa.com/app.js", "script"): "continue",
             ("https://prod.danawa.com/info/?pcode=1", "document"): "continue"}
    for (url, kind), expected in cases.items():
        route = FakeRoute(url, kind)
        b._filter(route)
        assert route.result == expected, (url, kind)


def test_collect_if_due_skips_when_this_slot_is_done(monkeypatch):
    """예약 실행은 불규칙하므로 KST 6시간 구간(0·6·12·18시 시작)마다 한 번만 수집한다"""
    monkeypatch.setenv("COLLECT_IF_DUE", "true")
    api = FakeApi([])
    api.status = lambda: {"last_collect_at": "2026-12-01T13:07:00"}
    monkeypatch.setattr(jobs, "now", lambda cfg: datetime(2026, 12, 1, 17, 40))
    assert jobs.collect(Config(), api)["status"] == "SKIPPED"
    monkeypatch.setattr(jobs, "now", lambda cfg: datetime(2026, 12, 1, 18, 5))
    assert jobs.collect(Config(), api)["status"] != "SKIPPED"
    assert jobs.slot_start(datetime(2026, 12, 1, 5, 59)) == datetime(2026, 12, 1, 0, 0)


def test_limit_products_keeps_highest_priority_first():
    items = [{"listing_id": i, "product_id": pid} for i, pid in enumerate([9, 9, 4, 4, 7, 7])]
    assert [l["listing_id"] for l in jobs.limit_products(items, 2)] == [0, 1, 2, 3]

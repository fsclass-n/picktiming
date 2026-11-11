"""실제 수집 카탈로그 동기화(PUT /rpa/catalog)와 비활성 쇼핑몰 상품 숨김"""
import json
from pathlib import Path
from urllib.parse import urlparse

from conftest import RPA

API = "/api/v1"
REAL_CATALOG = Path(__file__).resolve().parents[2] / "rpa" / "catalog.json"
DANAWA = {"name": "다나와(테스트)", "base_url": "https://prod.danawa.test"}
ENURI = {"name": "에누리(테스트)", "base_url": "https://www.enuri.test"}


def _catalog(**over):
    body = {
        "malls": [DANAWA, ENURI],
        "products": [{"model_no": "CAT-TEST-1", "name": "카탈로그 테스트 이어폰", "brand": "TestBrand", "category": "디지털",
                      "listings": [{"mall": DANAWA["name"], "url": "https://prod.danawa.test/info/?pcode=111"},
                                   {"mall": ENURI["name"], "url": "https://www.enuri.test/detail.jsp?modelno=222"}]}],
    }
    return {**body, **over}


def _search(client, h, q):
    return [p["model_no"] for p in client.get(f"{API}/products/search?q={q}", headers=h).json()["items"]]


def test_catalog_requires_rpa_key(client):
    assert client.put(f"{API}/rpa/catalog", json=_catalog()).status_code == 401


def test_catalog_creates_then_updates_idempotently(client, user_h):
    first = client.put(f"{API}/rpa/catalog", headers=RPA, json=_catalog()).json()
    assert (first["products_created"], first["listings_created"]) == (1, 2)
    again = client.put(f"{API}/rpa/catalog", headers=RPA, json=_catalog()).json()
    assert (again["products_created"], again["listings_created"], again["listings_updated"]) == (0, 0, 0)

    moved = _catalog()
    moved["products"][0]["name"] = "카탈로그 테스트 이어폰 2세대"
    moved["products"][0]["listings"][0]["url"] = "https://prod.danawa.test/info/?pcode=333"
    upd = client.put(f"{API}/rpa/catalog", headers=RPA, json=moved).json()
    assert (upd["products_updated"], upd["listings_updated"]) == (1, 1)

    urls = {i["url"] for i in client.get(f"{API}/rpa/listings", headers=RPA).json()["items"] if i["model_no"] == "CAT-TEST-1"}
    assert urls == {"https://prod.danawa.test/info/?pcode=333", "https://www.enuri.test/detail.jsp?modelno=222"}
    assert "CAT-TEST-1" in _search(client, user_h, "카탈로그")


def test_catalog_rejects_listing_outside_mall_domain(client):
    bad = _catalog()
    bad["products"][0]["listings"][0]["url"] = "https://evil.test/info/?pcode=1"
    r = client.put(f"{API}/rpa/catalog", headers=RPA, json=bad)
    assert r.status_code == 400 and r.json()["code"] == "LISTING_DOMAIN_MISMATCH"
    unknown = _catalog()
    unknown["products"][0]["listings"][0]["mall"] = "없는몰"
    assert client.put(f"{API}/rpa/catalog", headers=RPA, json=unknown).json()["code"] == "UNKNOWN_MALL"
    assert client.put(f"{API}/rpa/catalog", headers=RPA, json={**_catalog(), "products": [{**_catalog()["products"][0], "model_no": "-"}]}).status_code == 422


def test_retired_mall_hides_products_and_stops_collection(client, user_h):
    """가상 쇼핑몰 비활성(retire_mall_hosts): 데이터는 남기고 검색·수집 대상에서만 빠진다. 다시 등록하면 복구"""
    temp = {"name": "은퇴 테스트몰", "base_url": "https://retire.test"}
    body = {"malls": [temp], "products": [{"model_no": "RETIRE-1", "name": "은퇴 테스트 상품", "category": "기타",
                                           "listings": [{"mall": temp["name"], "url": "https://retire.test/p/1"}]}]}
    client.put(f"{API}/rpa/catalog", headers=RPA, json=body)
    assert "RETIRE-1" in _search(client, user_h, "은퇴")

    res = client.put(f"{API}/rpa/catalog", headers=RPA, json={**_catalog(), "retire_mall_hosts": ["retire.test"]}).json()
    assert res["malls_retired"] == 1
    assert "RETIRE-1" not in _search(client, user_h, "은퇴")
    assert all(i["model_no"] != "RETIRE-1" for i in client.get(f"{API}/rpa/listings", headers=RPA).json()["items"])
    assert client.get(f"{API}/products/search?q=", headers=user_h).json()["items"]  # 다른 상품은 그대로

    client.put(f"{API}/rpa/catalog", headers=RPA, json=body)  # 카탈로그에 다시 넣으면 활성화
    assert "RETIRE-1" in _search(client, user_h, "은퇴")


def test_home_deals_skip_retired_demo_products_and_fill_with_collected_ones(client):
    """홈(오늘, 눈여겨볼 가격): 비활성 시연 쇼핑몰 상품은 빼고, 점수 있는 상품이 모자라면 가격이 수집된 인기 상품(이미지 먼저)으로 채운다"""
    seed = [{"name": n, "base_url": f"https://mall-{c}.example.com"} for n, c in (("쇼핑몰 A", "a"), ("쇼핑몰 B", "b"), ("쇼핑몰 C", "c"))]
    new = {"model_no": "HOME-NEW-1", "name": "홈 신규 상품", "category": "디지털", "priority": 500, "image_url": "https://maker.example/n.png",
           "listings": [{"mall": DANAWA["name"], "url": "https://prod.danawa.test/info/?pcode=777"}]}
    client.put(f"{API}/rpa/catalog", headers=RPA, json={"malls": [DANAWA], "products": [new], "retire_mall_hosts": [m["base_url"][8:] for m in seed]})
    try:
        lid = next(i["listing_id"] for i in client.get(f"{API}/rpa/listings", headers=RPA).json()["items"] if i["model_no"] == "HOME-NEW-1")
        client.post(f"{API}/rpa/prices/bulk", headers=RPA, json={"items": [{"listing_id": lid, "price": 150000}]})
        deals = client.get(f"{API}/deals/today").json()
        models = [d["model_no"] for d in deals["timing"]]
        assert "HOME-NEW-1" in models and models.index("HOME-NEW-1") == 0  # 판단 보류지만 인기·이미지 있는 상품이 먼저
        demo = {i["model_no"] for i in client.get(f"{API}/rpa/listings", headers=RPA).json()["items"]}
        assert set(models) <= demo and all(d["model_no"] in demo for d in deals["drops"])  # 활성 판매처 상품만
    finally:  # 다른 테스트가 쓰는 시연 쇼핑몰을 되살린다
        client.put(f"{API}/rpa/catalog", headers=RPA, json={"malls": seed, "products": []})


def test_official_mall_is_marked_in_compare(client, user_h):
    """제조사 공식몰(kind=official)은 비교 표에 mall_kind=official로 나와 화면이 '공식몰 정가'로 표시한다"""
    lg = {"name": "LG전자 공식몰(테스트)", "base_url": "https://www.lge.test", "kind": "official"}
    prod = {"model_no": "OFFICIAL-1", "name": "공식몰 테스트 TV", "category": "가전",
            "listings": [{"mall": DANAWA["name"], "url": "https://prod.danawa.test/info/?pcode=4401"},
                         {"mall": lg["name"], "url": "https://www.lge.test/product/tvs/official-1"}]}
    assert client.put(f"{API}/rpa/catalog", headers=RPA, json={"malls": [DANAWA, lg], "products": [prod]}).status_code == 200
    items = [i for i in client.get(f"{API}/rpa/listings", headers=RPA).json()["items"] if i["model_no"] == "OFFICIAL-1"]
    client.post(f"{API}/rpa/prices/bulk", headers=RPA, json={"items": [{"listing_id": i["listing_id"], "price": 900000 if "lge" in i["url"] else 800000}
                                                                       for i in items]})
    rows = client.get(f"{API}/products/{items[0]['product_id']}/compare", headers=user_h).json()["items"]
    assert {r["mall"]: r["mall_kind"] for r in rows} == {DANAWA["name"]: "compare", lg["name"]: "official"}
    assert client.put(f"{API}/rpa/catalog", headers=RPA, json={"malls": [{**lg, "kind": "shop"}], "products": []}).status_code == 422


def test_catalog_hash_is_reported_for_skipping_unchanged_syncs(client):
    """수집기가 보낸 catalog.json 해시를 기록하고 GET /rpa/status로 돌려준다(같으면 다음 수집에서 동기화 생략)"""
    assert client.put(f"{API}/rpa/catalog?hash=abc123", headers=RPA, json=_catalog()).status_code == 200
    s = client.get(f"{API}/rpa/status", headers=RPA).json()
    assert s["catalog_hash"] == "abc123" and s["catalog_synced_at"]
    assert client.put(f"{API}/rpa/catalog?hash=not-hex!", headers=RPA, json=_catalog()).status_code == 422


def test_catalog_never_retires_a_mall_it_also_registers(client):
    res = client.put(f"{API}/rpa/catalog", headers=RPA, json={**_catalog(), "retire_mall_hosts": ["prod.danawa.test"]}).json()
    assert res["malls_retired"] == 0


def test_catalog_sets_priority_image_and_listing_order(client):
    hi = {"model_no": "PRIO-HI", "name": "우선 상품", "category": "디지털", "priority": 900, "image_url": "https://maker.example/hi.png",
          "listings": [{"mall": DANAWA["name"], "url": "https://prod.danawa.test/info/?pcode=901"}]}
    client.put(f"{API}/rpa/catalog", headers=RPA, json={"malls": [DANAWA], "products": [hi]})
    first = client.get(f"{API}/rpa/listings", headers=RPA).json()["items"][0]
    assert first["model_no"] == "PRIO-HI" and first["priority"] == 900
    bad = {**hi, "image_url": "http://insecure.example/x.png"}
    assert client.put(f"{API}/rpa/catalog", headers=RPA, json={"malls": [DANAWA], "products": [bad]}).status_code == 422


def test_real_catalog_file_is_accepted(client):
    """rpa/catalog.json 자체 검증: API가 받아들이고, 모든 상품에 다나와가 있으며(에누리는 같은 제품이 확인된 경우만), 이미지는 https"""
    body = {k: v for k, v in json.loads(REAL_CATALOG.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    assert all(isinstance(h, str) and h for h in body.pop("retire_mall_hosts", []))  # 시연 쇼핑몰 비활성화는 다른 테스트가 쓰는 데이터라 여기서는 보내지 않는다
    r = client.put(f"{API}/rpa/catalog", headers=RPA, json=body)
    assert r.status_code == 200, r.text
    models = [p["model_no"] for p in body["products"]]
    assert len(models) == len(set(models))
    assert len(models) <= 600  # 카탈로그 API 상한(schemas.CatalogIn) · Render 무료 플랜·수집 1회 시간 기준(docs/md/04-rpa.md)
    for p in body["products"]:
        malls = [l["mall"] for l in p["listings"]]
        assert "다나와" in malls and len(malls) == len(set(malls)) and set(malls) <= {"다나와", "에누리", "LG전자 공식몰", "삼성닷컴"}, p["model_no"]
        assert urlparse(p.get("image_url") or "https://x").scheme == "https", p["model_no"]

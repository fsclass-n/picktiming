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
    assert len(models) <= 400  # 수집 1일 1회 이상 + 상대 사이트 부담 상한(docs/md/04-rpa.md)
    for p in body["products"]:
        malls = sorted(l["mall"] for l in p["listings"])
        assert malls in (["다나와"], ["다나와", "에누리"]), p["model_no"]
        assert urlparse(p.get("image_url") or "https://x").scheme == "https", p["model_no"]

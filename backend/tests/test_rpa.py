import base64

from conftest import RPA

from app.config import now_local

API = "/api/v1/rpa"


def test_rpa_key_required(client):
    r = client.get(f"{API}/listings")
    assert r.status_code == 401 and r.json()["code"] == "INVALID_RPA_KEY"
    assert client.get(f"{API}/listings", headers={"X-RPA-KEY": "wrong"}).status_code == 401


def test_listings_include_last_price(client):
    items = client.get(f"{API}/listings", headers=RPA).json()["items"]
    assert len(items) >= 36 and all("last_price" in i for i in items)


def _at(hour: int) -> str:
    """오늘 hour시 30분 (시드 가격은 매일 12:00이라 겹치지 않는 시간대)"""
    return now_local().replace(hour=hour, minute=30, second=0, microsecond=0).isoformat()


def test_bulk_prices_create_target_alert(client, user_h):
    listings = [i for i in client.get(f"{API}/listings", headers=RPA).json()["items"] if i["model_no"] == "MF800-3"]
    # 시드: 데모 사용자가 분유(MF800-3)를 목표가 80,000원으로 관심 등록
    res = client.post(f"{API}/prices/bulk", headers=RPA,
                      json={"collected_at": _at(1),
                            "items": [{"listing_id": l["listing_id"], "price": 70000, "shipping_fee": 0} for l in listings] +
                                     [{"listing_id": 999999, "price": 1}]}).json()
    assert res["inserted"] == len(listings) and res["skipped"] == 1 and res["alerts_created"] >= 1
    alerts = client.get("/api/v1/alerts", headers=user_h).json()
    assert any(a["type"] == "TARGET_PRICE" and "분유" in a["message"] for a in alerts["items"])
    # 24시간 안에는 같은 목표가 알림을 다시 보내지 않는다
    again = client.post(f"{API}/prices/bulk", headers=RPA,
                        json={"collected_at": _at(2), "items": [{"listing_id": l["listing_id"], "price": 69000} for l in listings]}).json()
    before = sum(a["type"] == "TARGET_PRICE" and "분유" in a["message"] for a in alerts["items"])
    after = sum(a["type"] == "TARGET_PRICE" and "분유" in a["message"]
                for a in client.get("/api/v1/alerts", headers=user_h).json()["items"])
    assert again["inserted"] == len(listings) and after == before
    assert client.post("/api/v1/alerts/read-all", headers=user_h).json()["updated"] >= 1


def test_bulk_prices_skip_same_hour(client):
    """EC2 수집기와 GitHub Actions 수집기가 같은 시간대에 보내도 한 번만 저장"""
    # 목록 순서는 DB마다 다르고, 다른 테스트가 등록한 가격 없는 판매처가 섞일 수 있다
    listing = next(i for i in client.get(f"{API}/listings", headers=RPA).json()["items"] if i["last_price"])
    body = {"items": [{"listing_id": listing["listing_id"], "price": listing["last_price"]}]}
    first = client.post(f"{API}/prices/bulk", headers=RPA, json={**body, "collected_at": _at(3)}).json()
    second = client.post(f"{API}/prices/bulk", headers=RPA,
                         json={**body, "collected_at": now_local().replace(hour=3, minute=59).isoformat()}).json()
    assert (first["inserted"], first["duplicate"]) == (1, 0)
    assert (second["inserted"], second["duplicate"]) == (0, 1)


def test_public_prices_and_logs(client):
    r = client.put(f"{API}/public-prices", headers=RPA, json={"items": [
        {"model_no": "W2L12", "good_id": "G1", "price": 8800, "survey_date": "2026-10-20"},
        {"model_no": "NOPE", "good_id": "G2", "price": 1, "survey_date": "2026-10-20"}]}).json()
    assert r == {"saved": 1, "unmatched": 1}
    log = client.post(f"{API}/logs", headers=RPA, json={"job_name": "collect_prices", "status": "SUCCESS", "collected": 3,
                                                       "failed": 0, "started_at": "2026-10-21T10:00:00"})
    assert log.status_code == 201


def test_model_upload_and_weekly_report(client):
    bad = client.post(f"{API}/models", headers=RPA, json={"version": "x", "algorithm": "y", "artifact_b64": "@@@"})
    assert bad.status_code == 400
    up = client.post(f"{API}/models", headers=RPA, json={"version": "upload-test", "algorithm": "none",
                                                          "artifact_b64": base64.b64encode(b"x").decode(), "activate": False})
    assert up.status_code == 201 and up.json()["active"] is False
    rep = client.get(f"{API}/reports/weekly", headers=RPA)
    assert rep.status_code == 200 and rep.content[:2] == b"PK"  # xlsx(zip)
    assert client.post(f"{API}/train", headers=RPA).status_code == 202


def test_ensure_listings_is_idempotent(client):
    body = {"name": "네이버쇼핑", "base_url": "https://search.shopping.naver.com",
            "url_template": "https://search.shopping.naver.com/search/all?query={query}"}
    first = client.post(f"{API}/ensure-listings", headers=RPA, json=body).json()
    again = client.post(f"{API}/ensure-listings", headers=RPA, json=body).json()
    assert first["created"] >= 12 and again["created"] == 0 and first["mall_id"] == again["mall_id"]
    urls = [i["url"] for i in client.get(f"{API}/listings", headers=RPA).json()["items"] if i["mall"] == "네이버쇼핑"]
    assert any("query=" in u and "%20" in u for u in urls)


def test_collect_status_reports_last_successful_collection(client):
    """수집기가 '이번 6시간 구간에 이미 수집했는지' 판단할 수 있도록 마지막 수집 시각을 알려 준다"""
    assert client.get(f"{API}/status").status_code == 401
    body = {"job_name": "collect_prices", "status": "SUCCESS", "collected": 26, "failed": 0,
            "started_at": "2026-12-01T06:07:00", "ended_at": "2026-12-01T06:08:00"}
    client.post(f"{API}/logs", headers=RPA, json=body)
    client.post(f"{API}/logs", headers=RPA, json={**body, "status": "FAIL", "started_at": "2026-12-01T13:07:00"})
    st = client.get(f"{API}/status", headers=RPA).json()
    assert st["last_collect_at"] >= "2026-12-01T06:07:00" and not st["last_collect_at"].startswith("2026-12-01T13")

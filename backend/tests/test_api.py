API = "/api/v1"


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_signup_login_me(client):
    body = {"email": "new@test.com", "password": "Passw0rd!x", "name": "신규"}
    assert client.post(f"{API}/auth/signup", json=body).status_code == 201
    dup = client.post(f"{API}/auth/signup", json=body)
    assert dup.status_code == 409 and dup.json()["code"] == "EMAIL_EXISTS"
    bad = client.post(f"{API}/auth/login", json={"email": "new@test.com", "password": "wrong-pass"})
    assert bad.status_code == 401 and bad.json()["code"] == "INVALID_CREDENTIALS"
    tok = client.post(f"{API}/auth/login", json={"email": "new@test.com", "password": "Passw0rd!x"}).json()["access_token"]
    assert client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {tok}"}).json()["role"] == "USER"


def test_validation_error_format(client):
    r = client.post(f"{API}/auth/signup", json={"email": "x", "password": "1", "name": ""})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


def test_requires_auth(client):
    r = client.get(f"{API}/watchlist")
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHORIZED"


def test_search_pages_filters_and_sorts(client, user_h):
    """상품이 많아도 빠짐없이 볼 수 있게 page·size로 나누고, 분류·정렬·'지금 구매' 필터는 서버가 전체에 적용한다"""
    def get(qs):
        return client.get(f"{API}/products/search?{qs}", headers=user_h).json()

    every = get("size=100")
    assert every["total"] == len(every["items"]) and every["total"] > 3
    first, second = get("size=2&page=1&sort=price"), get("size=2&page=2&sort=price")
    assert first["total"] == every["total"] and (first["page"], first["size"]) == (1, 2) and len(first["items"]) == 2
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
    prices = [i["lowest_price"] for i in get("size=100&sort=price")["items"] if i["lowest_price"] is not None]
    assert prices == sorted(prices)
    scores = [i["score"] for i in get("size=100&sort=score")["items"] if i["score"] is not None]
    assert scores == sorted(scores, reverse=True)
    cats = {i["category"] for i in get("size=100&category=가전,유아")["items"]}
    assert cats and cats <= {"가전", "유아"}
    assert all(i["label"] == "BUY_NOW" for i in get("size=100&buy_only=true")["items"])
    assert client.get(f"{API}/products/search?size=101", headers=user_h).status_code == 422


def test_search_and_compare(client, user_h):
    items = client.get(f"{API}/products/search?q=이어폰", headers=user_h).json()["items"]
    assert len(items) == 1 and items[0]["label"] in {"BUY_NOW", "WAIT_A_BIT", "WAIT"}
    c = client.get(f"{API}/products/7/compare", headers=user_h).json()
    assert len(c["items"]) == 3
    assert sum(i["is_lowest"] for i in c["items"]) >= 1
    assert any(not i["in_stock"] for i in c["items"])  # 시드: 무선 청소기 V8 쇼핑몰 C 품절
    lowest = next(i for i in c["items"] if i["is_lowest"])
    assert lowest["total_price"] == lowest["price"] + lowest["shipping_fee"] == c["lowest_total"]


def test_prices_chart(client, user_h):
    d = client.get(f"{API}/products/1/prices?days=30", headers=user_h).json()
    assert len(d["malls"]) == 3 and 28 <= len(d["dates"]) <= 31
    assert d["all_time_min"]["price"] <= min(v for v in d["lowest"] if v)
    assert client.get(f"{API}/products/1/prices?days=5", headers=user_h).json()["code"] == "INVALID_DAYS"


def test_timing(client, user_h):
    t = client.get(f"{API}/products/1/timing", headers=user_h).json()
    assert t["model_version"].startswith("rf-")
    assert 0 <= t["score"] <= 100 and 0 <= t["prob_drop_7d"] <= 1
    expected = round((1 - t["prob_drop_7d"]) * 70 + (1 - t["percentile_90d"]) * 30)
    assert abs(t["score"] - expected) <= 1
    hold = client.get(f"{API}/products/4/timing", headers=user_h).json()  # 이력 21일
    assert hold["label"] == "HOLD" and hold["score"] is None


def test_advice_template_and_cache(client, user_h):
    first = client.post(f"{API}/products/1/advice", headers=user_h).json()
    assert first["source"] == "template" and first["cached"] is False and len(first["reasons"]) >= 1
    second = client.post(f"{API}/products/1/advice", headers=user_h).json()
    assert second["cached"] is True and second["summary"] == first["summary"]


def test_chat_template(client, user_h):
    r = client.post(f"{API}/ai/chat", headers=user_h, json={"product_id": 1, "question": "역대 최저가는 언제였어?"}).json()
    assert "최저" in r["answer"]
    unknown = client.post(f"{API}/ai/chat", headers=user_h, json={"product_id": 1, "question": "배터리 수명은?"}).json()
    assert "답하기 어려운" in unknown["answer"]


def test_watchlist_crud(client, user_h):
    w = client.post(f"{API}/watchlist", headers=user_h, json={"product_id": 2, "target_price": 300000})
    assert w.status_code == 201
    wid = w.json()["id"]
    assert client.post(f"{API}/watchlist", headers=user_h, json={"product_id": 2}).status_code == 409
    assert client.patch(f"{API}/watchlist/{wid}", headers=user_h, json={"target_price": 1}).json()["target_price"] == 1
    assert client.delete(f"{API}/watchlist/{wid}", headers=user_h).status_code == 204
    assert all(i["id"] != wid for i in client.get(f"{API}/watchlist", headers=user_h).json()["items"])


def test_deals_today(client, user_h):
    d = client.get(f"{API}/deals/today", headers=user_h).json()
    scores = [x["score"] for x in d["timing"]]
    assert scores == sorted(scores, reverse=True) and len(d["drops"]) > 0


def test_deals_today_is_public(client):
    """홈 화면은 로그인 없이 볼 수 있다 (개인 정보가 없는 데이터)"""
    r = client.get(f"{API}/deals/today")
    assert r.status_code == 200 and r.json()["timing"]
    assert client.get(f"{API}/alerts").status_code == 401  # 알림은 여전히 로그인 필요


def test_register_url(client, user_h):
    bad = client.post(f"{API}/products", headers=user_h, json={"url": "https://unknown.example.org/p/1"})
    assert bad.status_code == 400 and bad.json()["code"] == "UNSUPPORTED_MALL"
    ok = client.post(f"{API}/products", headers=user_h, json={"url": "https://mall-a.example.com/products/NEW", "name": "신규"})
    assert ok.status_code == 201 and ok.json()["status"] == "PENDING"


def test_admin_requires_role(client, user_h, admin_h):
    assert client.get(f"{API}/admin/rpa-logs", headers=user_h).status_code == 403
    d = client.get(f"{API}/admin/rpa-logs", headers=admin_h).json()
    assert len(d["daily"]) == 7 and any(m["active"] for m in d["models"])
    m = client.get(f"{API}/admin/ai-metrics", headers=admin_h).json()
    assert m["summary"]["calls_7d"] >= 1

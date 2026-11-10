"""비밀번호 규칙, 테스트 계정 간편 로그인, 소셜 로그인(OAuth), 관리자 회원 관리"""
from urllib.parse import parse_qs, urlparse

import pytest

from app import oauth
from app.config import get_settings

API = "/api/v1"


@pytest.mark.parametrize("pw", ["short1!A", "alllowercase1!", "ALLUPPER1!", "NoDigits!!", "NoSpecial12", "Ab1!"])
def test_signup_rejects_weak_password(client, pw):
    r = client.post(f"{API}/auth/signup", json={"email": "weak@test.com", "password": pw, "name": "약한"})
    if pw == "short1!A":  # 정확히 8자이며 모든 조건 충족 → 허용
        assert r.status_code == 201
    else:
        assert r.status_code == 422 and "대문자" in r.json()["message"]


def test_providers_hide_secrets(client):
    d = client.get(f"{API}/auth/providers").json()
    assert d == {"demo_login": True, "google": False, "naver": False, "kakao": False}


def test_demo_login_user_and_admin(client):
    u = client.post(f"{API}/auth/demo-login", json={"kind": "user"}).json()
    a = client.post(f"{API}/auth/demo-login", json={"kind": "admin"}).json()
    assert u["user"]["email"] == "demo@timepick.demo" and u["user"]["role"] == "USER"
    assert a["user"]["role"] == "ADMIN" and a["access_token"]


def test_demo_login_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_login_enabled", False)
    r = client.post(f"{API}/auth/demo-login", json={"kind": "user"})
    assert r.status_code == 403 and r.json()["code"] == "DEMO_LOGIN_DISABLED"


def test_oauth_not_configured(client):
    r = client.get(f"{API}/auth/oauth/google/start", follow_redirects=False)
    assert r.status_code == 503 and r.json()["code"] == "OAUTH_NOT_CONFIGURED"
    assert client.get(f"{API}/auth/oauth/facebook/start").status_code == 404


def test_oauth_start_and_callback(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "naver_client_id", "cid")
    monkeypatch.setattr(s, "naver_client_secret", "secret")
    r = client.get(f"{API}/auth/oauth/naver/start?next=/watchlist", follow_redirects=False)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    q = parse_qs(url.query)
    assert url.netloc == "nid.naver.com" and q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://testserver/api/v1/auth/oauth/naver/callback"]

    monkeypatch.setattr(oauth, "fetch_profile", lambda *a: {"email": "Social@Naver.com", "name": "네이버 사용자"})
    cb = client.get(f"{API}/auth/oauth/naver/callback", params={"code": "c", "state": q["state"][0]}, follow_redirects=False)
    loc = cb.headers["location"]
    assert cb.status_code == 302 and loc.startswith("/oauth/callback#token=") and loc.endswith("next=/watchlist")
    token = loc.split("token=")[1].split("&")[0]
    assert client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "social@naver.com"

    forged = client.get(f"{API}/auth/oauth/naver/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert forged.headers["location"].startswith("/login?oauth_error=")


def test_oauth_next_blocks_open_redirect():
    assert oauth.safe_next("https://evil.example") == "/" and oauth.safe_next("//evil") == "/" and oauth.safe_next("/a?b=1") == "/a?b=1"


def test_oauth_profile_normalize():
    assert oauth.normalize("kakao", {"id": 7, "kakao_account": {"profile": {"nickname": "라이언"}}}) == {"email": "kakao_7@kakao.oauth", "name": "라이언"}
    assert oauth.normalize("naver", {"response": {"id": "x", "email": "a@b.c", "name": "홍"}})["email"] == "a@b.c"


def _real_admin(client):
    """테스트 관리자(admin@timepick.demo)는 조회만 가능하므로 ADMIN_EMAILS로 실제 관리자를 만든다"""
    s = get_settings()
    s.__dict__["admin_emails"] = "boss@test.com"
    body = {"email": "boss@test.com", "password": "Boss!2345", "name": "관리자"}
    client.post(f"{API}/auth/signup", json=body)
    tok = client.post(f"{API}/auth/login", json={"email": body["email"], "password": body["password"]}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_admin_users_list_and_role_change(client, user_h, admin_h):
    assert client.get(f"{API}/admin/users", headers=user_h).status_code == 403
    d = client.get(f"{API}/admin/users?q=demo", headers=admin_h).json()
    demo = next(u for u in d["items"] if u["email"] == "demo@timepick.demo")
    assert d["total"] >= 1 and d["summary"]["admins"] >= 1 and demo["watch_count"] >= 1

    ro = client.patch(f"{API}/admin/users/{demo['id']}/role", headers=admin_h, json={"role": "ADMIN"})
    assert ro.status_code == 403 and ro.json()["code"] == "DEMO_READ_ONLY"

    boss = _real_admin(client)
    up = client.patch(f"{API}/admin/users/{demo['id']}/role", headers=boss, json={"role": "ADMIN"})
    assert up.status_code == 200 and up.json()["role"] == "ADMIN"
    down = client.patch(f"{API}/admin/users/{demo['id']}/role", headers=boss, json={"role": "USER"})
    assert down.json()["role"] == "USER"
    me = client.get(f"{API}/users/me", headers=boss).json()
    assert client.patch(f"{API}/admin/users/{me['id']}/role", headers=boss, json={"role": "USER"}).json()["code"] == "SELF_ROLE_CHANGE"
    assert client.patch(f"{API}/admin/users/{demo['id']}/role", headers=boss, json={"role": "OWNER"}).status_code == 422
    assert client.get(f"{API}/admin/users?role=ADMIN", headers=admin_h).json()["items"][0]["role"] == "ADMIN"


@pytest.mark.parametrize("legacy", ["demo@picktiming.demo", "demo@buytiming.demo"])
def test_demo_login_finds_accounts_seeded_before_rename(client, legacy):
    """이름 변경(BuyTiming → PickTiming → TimePick) 전 시드된 운영 DB: 이전 이메일의 테스트 계정으로도 간편 로그인된다"""
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "demo@timepick.demo").one()
        u.email = legacy
        db.commit()
    try:
        r = client.post(f"{API}/auth/demo-login", json={"kind": "user"})
        assert r.status_code == 200 and r.json()["user"]["email"] == legacy
    finally:
        with SessionLocal() as db:
            db.query(User).filter(User.email == legacy).one().email = "demo@timepick.demo"
            db.commit()


def test_legacy_test_admin_stays_read_only(client):
    from app.routers.admin import DEMO_ADMINS

    assert {"admin@timepick.demo", "admin@picktiming.demo"} <= DEMO_ADMINS

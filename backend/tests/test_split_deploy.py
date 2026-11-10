"""Render 분리 배포: 백엔드(Web Service)는 API만 제공하고 화면은 프런트엔드(Static Site)가 담당"""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import oauth
from app.config import Settings, get_settings
from app.main import create_app

WEB = "https://timepick.onrender.com"


@pytest.fixture
def api_only(tmp_path):
    """FRONTEND_DIR가 없는 API 전용 이미지(backend/Dockerfile)와 같은 구성"""
    s = Settings(frontend_dir=str(tmp_path / "missing"), frontend_url=f"{WEB}/", allowed_origins="http://localhost:5173")
    return TestClient(create_app(s))


def test_settings_add_frontend_origin_to_cors():
    s = Settings(allowed_origins="http://localhost:5173", frontend_url=f"{WEB}/login")
    assert s.origins == ["http://localhost:5173", WEB]
    assert Settings(allowed_origins="*", frontend_url=WEB).origins == ["*"]
    assert Settings(allowed_origins=f"{WEB},http://localhost:5173", frontend_url=WEB).origins == [WEB, "http://localhost:5173"]
    assert Settings(frontend_url="").frontend_link("/login?x=1") == "/login?x=1"
    assert Settings(frontend_url=f"{WEB}/").frontend_link("/login") == f"{WEB}/login"


@pytest.mark.parametrize("bad", ["timepick.onrender.com", "ftp://example.com", "https://"])
def test_settings_reject_invalid_frontend_url(bad):
    with pytest.raises(ValueError):
        Settings(frontend_url=bad)


def test_api_only_redirects_screens_to_frontend(api_only):
    """기존 주소(https://timepick-ai.onrender.com)로 들어온 화면 요청은 Static Site로 보낸다"""
    root = api_only.get("/", follow_redirects=False)
    assert root.status_code == 302 and root.headers["location"] == f"{WEB}/"
    deep = api_only.get("/product/3?tab=chart", follow_redirects=False)
    assert deep.status_code == 302 and deep.headers["location"] == f"{WEB}/product/3?tab=chart"


def test_api_only_keeps_api_docs_and_health(api_only):
    assert api_only.get("/health").json()["status"] == "ok"
    assert api_only.get("/docs").status_code == 200
    assert api_only.get("/openapi.json").status_code == 200
    assert api_only.get("/api/v1/users/me").json()["code"] == "UNAUTHORIZED"
    missing = api_only.get("/api/v1/no-such-endpoint", follow_redirects=False)
    assert missing.status_code == 404 and "location" not in missing.headers
    assert api_only.get("/js/config.js", follow_redirects=False).headers["location"] == f"{WEB}/js/config.js"


def test_api_only_without_frontend_url_returns_service_info(tmp_path):
    """EC2 api 컨테이너: 화면은 nginx가 제공하므로 API 안내만 응답"""
    c = TestClient(create_app(Settings(frontend_dir=str(tmp_path / "missing"), frontend_url="")))
    assert c.get("/", follow_redirects=False).json() == {"service": "TimePick API", "docs": "/docs", "health": "/health"}
    assert c.get("/login").status_code == 404


def test_cors_preflight_allows_only_configured_origins(api_only):
    headers = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    ok = api_only.options("/api/v1/auth/login", headers={"Origin": WEB, **headers})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == WEB
    assert "authorization" in ok.headers["access-control-allow-headers"].lower()
    blocked = api_only.options("/api/v1/auth/login", headers={"Origin": "https://evil.example", **headers})
    assert blocked.status_code == 400 and "access-control-allow-origin" not in blocked.headers
    simple = api_only.get("/health", headers={"Origin": WEB})
    assert simple.headers["access-control-allow-origin"] == WEB


def test_oauth_returns_to_frontend_url(client, monkeypatch):
    """분리 배포에서는 로그인 완료·실패 후 API 도메인이 아니라 화면 도메인으로 돌아간다"""
    s = get_settings()
    monkeypatch.setattr(s, "naver_client_id", "cid")
    monkeypatch.setattr(s, "naver_client_secret", "secret")
    monkeypatch.setattr(s, "frontend_url", WEB)
    start = client.get("/api/v1/auth/oauth/naver/start?next=/alerts", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    monkeypatch.setattr(oauth, "fetch_profile", lambda *a: {"email": "split@naver.com", "name": "분리 배포"})
    done = client.get("/api/v1/auth/oauth/naver/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert done.headers["location"].startswith(f"{WEB}/oauth/callback#token=") and done.headers["location"].endswith("next=/alerts")
    failed = client.get("/api/v1/auth/oauth/naver/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert failed.headers["location"].startswith(f"{WEB}/login?oauth_error=")

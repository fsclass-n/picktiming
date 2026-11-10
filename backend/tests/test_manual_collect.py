"""관리자 화면의 '지금 수집' 버튼: 실제 관리자만 GitHub Actions 수집 워크플로를 실행할 수 있다"""
import httpx
import pytest
from test_auth_admin import _real_admin

from app.config import get_settings

API = "/api/v1/admin/collect"


class FakeResp:
    def __init__(self, code):
        self.status_code, self.text = code, ""


@pytest.fixture
def github(monkeypatch):
    calls = []
    monkeypatch.setattr(get_settings(), "github_dispatch_token", "ghp_test")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append((url, kw)) or FakeResp(204))
    return calls


def test_user_and_test_admin_cannot_trigger(client, user_h, admin_h, github):
    assert client.post(API, headers=user_h).status_code == 403
    st = client.get(API, headers=admin_h).json()
    assert st["allowed"] is False and "테스트 관리자" in st["reason"]
    r = client.post(API, headers=admin_h)
    assert r.status_code == 403 and r.json()["code"] == "DEMO_READ_ONLY" and github == []


def test_real_admin_triggers_workflow_once_per_cooldown(client, github):
    boss = _real_admin(client)
    assert client.get(API, headers=boss).json()["allowed"] is True
    r = client.post(API, headers=boss)
    assert r.status_code == 202 and r.json()["status"] == "REQUESTED"
    url, kw = github[0]
    assert url.endswith("/repos/fsclass-n/timepick/actions/workflows/collect-render.yml/dispatches")
    assert kw["json"] == {"ref": "main", "inputs": {"job": "collect"}} and kw["headers"]["Authorization"] == "Bearer ghp_test"
    again = client.post(API, headers=boss)
    assert again.status_code == 429 and again.json()["code"] == "COLLECT_TOO_SOON" and len(github) == 1


def test_trigger_reports_missing_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "github_dispatch_token", "")
    boss = _real_admin(client)
    assert client.get(API, headers=boss).json()["configured"] is False
    assert client.post(API, headers=boss).json()["code"] == "COLLECT_NOT_CONFIGURED"

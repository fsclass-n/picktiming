import os
import pathlib
import tempfile

import pytest

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="timepick-test-"))
# React 빌드 결과(frontend/dist)와 같은 모양의 임시 폴더 — CI에서는 npm 빌드 없이 백엔드만 테스트한다
_DIST = _TMP / "dist"
(_DIST / "assets").mkdir(parents=True)
(_DIST / "index.html").write_text('<!doctype html><title>타임픽</title><script src="/js/config.js"></script><div id="root"></div>',
                                  encoding="utf-8")
(_DIST / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
# CI의 MySQL 통합 테스트는 TEST_DATABASE_URL로 지정, 기본은 임시 SQLite
os.environ.update({
    "DATABASE_URL": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "JWT_SECRET": "test-secret",
    "RPA_API_KEY": "test-rpa-key",
    "GEMINI_API_KEY": "",
    "SEED_DEMO_PASSWORD": "demo-pass-1",
    "SEED_ADMIN_PASSWORD": "admin-pass-1",
    "APP_ENV": "test",
    # Render 단독 풀스택 구성(프런트엔드 동시 서빙)으로 전체 테스트를 실행한다
    "FRONTEND_DIR": str(_DIST),
    "DEMO_LOGIN_ENABLED": "true",
    # 로컬 .env에 실제 소셜 로그인 키가 있어도 테스트는 '미설정' 상태로 시작한다(환경 변수가 .env보다 우선)
    **{f"{p}_CLIENT_{k}": "" for p in ("GOOGLE", "NAVER", "KAKAO") for k in ("ID", "SECRET")},
    "PUBLIC_BASE_URL": "",
    "ADMIN_EMAILS": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

RPA = {"X-RPA-KEY": "test-rpa-key"}


@pytest.fixture(scope="session")
def client():
    seed(reset=True)
    with TestClient(app) as c:
        yield c


def _token(client, email, pw):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def user_h(client):
    return _token(client, "demo@timepick.demo", "demo-pass-1")


@pytest.fixture(scope="session")
def admin_h(client):
    return _token(client, "admin@timepick.demo", "admin-pass-1")

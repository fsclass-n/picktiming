"""DB 연결 실패 안내: Render 로그에서 원인(DB 이름·계정·접속)을 바로 알 수 있게 하고, 비밀번호는 노출하지 않는다"""
import pymysql
import pytest
from sqlalchemy.exc import OperationalError

from app.database import describe_db_error

URL = "mysql+pymysql://abc.root:S3cret!Pass@gateway01.ap-northeast-1.prod.aws.tidbcloud.com:4000/timepick?charset=utf8mb4"


def _err(code: int, msg: str) -> OperationalError:
    return OperationalError("SELECT 1", {}, pymysql.err.OperationalError(code, msg))


def test_unknown_database_names_the_database_and_fix():
    text = describe_db_error(_err(1049, "Unknown database 'timepick'"), URL)
    assert "'timepick'" in text and "DATABASE_URL" in text and "picktiming" in text
    assert "S3cret" not in text and "abc.root" not in text


@pytest.mark.parametrize(("code", "hint"), [(1045, "사용자 이름 또는 비밀번호"), (2003, "호스트"), (9999, "9999")])
def test_other_connection_errors_have_specific_hints(code, hint):
    text = describe_db_error(_err(code, "boom"), URL)
    assert hint in text and "S3cret" not in text


def test_startup_turns_db_error_into_clear_message(monkeypatch):
    """앱 시작(lifespan)에서 DB 오류가 나면 원인 안내 문구로 기동을 멈춘다"""
    from fastapi.testclient import TestClient

    from app import main
    from app.config import Settings

    def broken():
        raise _err(1049, "Unknown database 'timepick'")

    monkeypatch.setattr(main, "init_db", broken)
    app = main.create_app(Settings(database_url=URL, frontend_url=""))
    with pytest.raises(RuntimeError, match="DATABASE_URL의 데이터베이스 'timepick'"):
        with TestClient(app):
            pass

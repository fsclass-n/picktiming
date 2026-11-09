import os
import ssl
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def _ca_file(path: str) -> str | None:
    """DB_SSL_CA 파일이 있으면 그대로, 없으면(예: Windows 로컬) certifi 번들, 그것도 없으면 OS 기본 인증서 저장소"""
    if os.path.isfile(path):
        return path
    try:
        import certifi

        return certifi.where()
    except ImportError:
        return None


def connect_args(s: Settings) -> dict:
    if s.database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    if s.db_ssl_ca:
        # TiDB 등 TLS 필수 DB: 인증서·호스트 이름을 검증한다. 같은 .env를 컨테이너(Linux)와 Windows 로컬에서 함께 쓸 수 있다.
        return {"ssl": ssl.create_default_context(cafile=_ca_file(s.db_ssl_ca))}
    return {}


def _engine():
    s = get_settings()
    return create_engine(s.database_url, pool_pre_ping=True, pool_recycle=280, connect_args=connect_args(s))


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (모델 등록)

    Base.metadata.create_all(engine)


def describe_db_error(exc: OperationalError, database_url: str) -> str:
    """DB 연결 실패를 원인별 안내 문구로 바꾼다(Render 로그용). 접속 주소의 사용자·비밀번호는 넣지 않는다"""
    code = (getattr(exc.orig, "args", None) or [None])[0]
    url = make_url(database_url)
    where = f"{url.host}:{url.port}" if url.host else "(호스트 없음)"
    if code == 1049:
        return (f"DATABASE_URL의 데이터베이스 '{url.database}'가 {where}에 없습니다. "
                "운영 데이터는 TiDB의 'picktiming' 데이터베이스에 있으므로 DATABASE_URL 경로를 /picktiming 으로 지정하세요. "
                "서비스·도메인 이름(예: timepick)을 바꿔도 DB 이름은 바꾸지 않습니다.")
    if code == 1045:
        return f"DB 사용자 이름 또는 비밀번호가 올바르지 않습니다({where}). TiDB Connect 화면의 값과 DATABASE_URL을 비교하세요(특수문자는 URL 인코딩)."
    if code in (2003, 2005, 2006, 2013):
        return f"DB 서버({where})에 접속할 수 없습니다. 호스트·포트(TiDB 4000)와 네트워크, DB_SSL_CA 설정을 확인하세요."
    return f"DB 연결 실패(오류 코드 {code}, {where}): {getattr(exc.orig, 'args', [None, ''])[-1]}"

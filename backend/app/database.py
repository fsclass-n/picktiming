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
    if s.database_url.startswith("sqlite"):
        return create_engine(s.database_url, pool_pre_ping=True, connect_args=connect_args(s))
    # 연결 수를 작게 유지하고(무료 한도의 RU·연결 보호), 서버가 끊기 전에 교체하며, 끊긴 연결은 자동 재연결한다
    return create_engine(s.database_url, pool_size=s.db_pool_size, max_overflow=s.db_max_overflow, pool_timeout=10,
                         pool_pre_ping=True, pool_recycle=280, connect_args=connect_args(s))


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
    _add_missing_columns()


# create_all은 이미 있는 테이블에 새 칸을 만들지 않는다. 데이터를 지우지 않고 칸만 추가한다(TiDB·MySQL·SQLite 공통 문법)
NEW_COLUMNS = {
    "products": {"priority": "INTEGER NOT NULL DEFAULT 0", "image_url": "VARCHAR(500) NULL", "spec_summary": "VARCHAR(500) NULL"},
    "product_listings": {"offer_count": "INTEGER NULL", "high_price": "INTEGER NULL", "rating": "FLOAT NULL", "review_count": "INTEGER NULL"},
}


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in NEW_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


PRODUCTION_DB = "timepick"  # 운영 TiDB 데이터베이스 이름(2026-11-09 picktiming → timepick, RENAME TABLE로 이전)


def describe_db_error(exc: OperationalError, database_url: str) -> str:
    """DB 연결 실패를 원인별 안내 문구로 바꾼다(Render 로그용). 접속 주소의 사용자·비밀번호는 넣지 않는다"""
    code = (getattr(exc.orig, "args", None) or [None])[0]
    url = make_url(database_url)
    where = f"{url.host}:{url.port}" if url.host else "(호스트 없음)"
    if code == 1049:
        return (f"DATABASE_URL의 데이터베이스 '{url.database}'가 {where}에 없습니다. "
                f"운영 데이터는 TiDB의 '{PRODUCTION_DB}' 데이터베이스에 있으므로 DATABASE_URL 경로를 /{PRODUCTION_DB} 로 지정하세요. "
                "TiDB Cloud SQL Editor에서 SHOW DATABASES; 로 실제 이름을 확인할 수 있습니다.")
    if code == 1045:
        return f"DB 사용자 이름 또는 비밀번호가 올바르지 않습니다({where}). TiDB Connect 화면의 값과 DATABASE_URL을 비교하세요(특수문자는 URL 인코딩)."
    if code in (2003, 2005, 2006, 2013):
        return f"DB 서버({where})에 접속할 수 없습니다. 호스트·포트(TiDB 4000)와 네트워크, DB_SSL_CA 설정을 확인하세요."
    return f"DB 연결 실패(오류 코드 {code}, {where}): {getattr(exc.orig, 'args', [None, ''])[-1]}"

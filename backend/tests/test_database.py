"""하나의 .env를 Windows 로컬·Linux 컨테이너(EC2·Render)에서 함께 쓰기 위한 DB 접속 옵션"""
import ssl

from app.config import Settings
from app.database import connect_args

TIDB = "mysql+pymysql://u.root:p@gateway01.example.prod.aws.tidbcloud.com:4000/timepick?charset=utf8mb4"


def test_sqlite_has_no_tls():
    assert connect_args(Settings(database_url="sqlite:///x.db", db_ssl_ca="/etc/ssl/certs/ca-certificates.crt")) == {
        "check_same_thread": False}


def test_mysql_without_ca_has_no_tls():
    """CI의 MySQL 8 테스트처럼 DB_SSL_CA가 비어 있으면 TLS를 쓰지 않는다"""
    assert connect_args(Settings(database_url=TIDB, db_ssl_ca="")) == {}


def test_tidb_tls_verifies_even_when_ca_path_is_missing():
    """Windows 로컬에는 /etc/ssl/certs/... 가 없어도 인증서·호스트 이름 검증이 켜진 TLS로 접속한다"""
    ctx = connect_args(Settings(database_url=TIDB, db_ssl_ca="/no/such/ca.crt"))["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert ctx.cert_store_stats()["x509_ca"] > 0  # certifi(또는 OS) 루트 인증서가 로드됨


def test_tidb_tls_uses_given_ca_file(tmp_path):
    import certifi

    ca = tmp_path / "ca.pem"
    ca.write_bytes(open(certifi.where(), "rb").read())
    ctx = connect_args(Settings(database_url=TIDB, db_ssl_ca=str(ca)))["ssl"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.cert_store_stats()["x509_ca"] > 0

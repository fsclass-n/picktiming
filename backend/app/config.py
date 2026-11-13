from datetime import datetime
from functools import lru_cache
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULTS = {"change-me", "change-me-rpa", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./timepick.db"
    db_ssl_ca: str | None = None  # 값이 있으면 TLS 접속(TiDB 필수). 파일이 없는 환경(Windows 로컬)은 certifi/OS 인증서로 검증

    # DB 연결 풀(TiDB Starter 무료: 프로젝트마다 인스턴스 1개 권장). Render 무료 인스턴스 1대 기준 최대 5개 연결
    db_pool_size: int = 3
    db_max_overflow: int = 2
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60
    rpa_api_key: str = "change-me-rpa"
    admin_emails: str = ""  # 쉼표 구분, 가입 시 관리자 권한 부여

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_daily_limit: int = 20

    # 테스트 계정 간편 로그인(시드의 demo@·admin@timepick.demo). 시연용 — 실제 운영에서는 false
    demo_login_enabled: bool = False

    # 소셜 로그인(OAuth). 값이 있는 제공자만 버튼이 활성화된다. 콜백 주소: <서비스 주소>/api/v1/auth/oauth/<provider>/callback
    google_client_id: str = ""
    google_client_secret: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    kakao_client_id: str = ""  # 카카오 REST API 키
    kakao_client_secret: str = ""  # 카카오 Client Secret(사용 설정한 경우만)
    public_base_url: str = ""  # OAuth 콜백 주소의 기준. 비우면 요청 주소(프록시 헤더 반영)를 사용

    # 관리자 화면 '지금 수집' 버튼: GitHub Actions 수집 워크플로를 실행할 토큰(Actions: Read and write 권한만 있는 fine-grained 토큰). Render에만 등록
    github_dispatch_token: str = ""
    github_repo: str = "fsclass-n/timepick"
    # 쉼표 구분. Render Static Site·로컬 Vite처럼 다른 주소의 화면만 필요(EC2·로컬 풀스택은 같은 도메인, Netlify 데모는 API를 부르지 않음)
    allowed_origins: str = "*"
    tz: str = "Asia/Seoul"
    # 프런트엔드 정적 파일 폴더. 비우면 저장소의 frontend/를 찾아 있으면(로컬) 서빙, 없으면(EC2 api 컨테이너) API만 제공
    frontend_dir: str | None = None
    # 분리 배포한 프런트엔드 주소(Render Static Site, 예: https://timepick.onrender.com). 환경마다 다르므로 .env가 아닌 Render에만 등록한다.
    # 값이 있으면 CORS 허용 목록에 자동 추가, 소셜 로그인 후 이 주소로 복귀, API 전용 서버의 화면 경로(/, /login 등)를 이 주소로 보낸다.
    frontend_url: str = ""

    @field_validator("frontend_url")
    @classmethod
    def _check_frontend_url(cls, value: str) -> str:
        value = value.strip()
        if value:
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("FRONTEND_URL은 https://로 시작하는 전체 주소여야 합니다.")
        return value

    @property
    def frontend_origin(self) -> str:
        parts = urlsplit(self.frontend_url)
        return f"{parts.scheme}://{parts.netloc}" if self.frontend_url else ""

    def frontend_link(self, path: str) -> str:
        """화면 경로(/login 등)를 프런트엔드 주소 기준으로 바꾼다. FRONTEND_URL이 없으면(같은 도메인) 경로 그대로"""
        return f"{self.frontend_url.rstrip('/')}{path}" if self.frontend_url else path

    @property
    def origins(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]
        if self.frontend_origin and "*" not in origins and self.frontend_origin not in origins:
            origins.append(self.frontend_origin)
        return origins

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    def validate_for_production(self) -> None:
        if self.app_env == "production":
            weak = [k for k in ("jwt_secret", "rpa_api_key") if getattr(self, k) in INSECURE_DEFAULTS]
            if weak:
                raise RuntimeError(f"운영 환경에서는 {', '.join(weak)} 값을 반드시 설정해야 합니다.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def now_local() -> datetime:
    """DB에는 서비스 기준 시간대(KST)의 naive datetime으로 저장한다."""
    return datetime.now(ZoneInfo(get_settings().tz)).replace(tzinfo=None)

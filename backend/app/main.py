import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .database import describe_db_error, engine, init_db
from .errors import register_error_handlers
from .routers import admin, ai, auth, products, rpa, user_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SECURITY_HEADERS = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}
# 브라우저 화면이 실제로 쓰는 메서드·헤더만 허용한다(수집기의 X-RPA-KEY 요청은 서버 간 호출이라 CORS와 무관)
CORS_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Authorization", "Content-Type"]


class SPAStaticFiles(StaticFiles):
    """React(SPA) 라우팅: /search 같은 화면 경로는 index.html로, 확장자가 있는 파일만 실제 404"""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


def _mount_frontend(app: FastAPI, frontend_dir: Path) -> None:
    """로컬 풀스택(npm run build 결과)·이전 통합 이미지: 프런트엔드와 API를 같은 도메인으로 제공"""

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    @app.get("/js/config.js", include_in_schema=False)
    def frontend_config():
        return Response('window.APP_CONFIG = { API_BASE_URL: "/" };\n', media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})

    app.mount("/", SPAStaticFiles(directory=frontend_dir, html=True), name="frontend")


def _redirect_screens(app: FastAPI, settings: Settings) -> None:
    """API 전용 서버(Render 분리 배포): 기존 주소로 들어온 화면 요청(/, /login, /product/3 …)을 Static Site로 보낸다"""

    @app.get("/{path:path}", include_in_schema=False)
    def to_frontend(path: str, request: Request):
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(settings.frontend_link(f"/{path}{query}"), status_code=302)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.validate_for_production()
        try:
            init_db()
        except OperationalError as exc:  # 긴 드라이버 오류 대신 원인과 고칠 값을 로그 첫 줄에 남기고 기동을 멈춘다
            raise RuntimeError(describe_db_error(exc, settings.database_url)) from exc
        yield

    app = FastAPI(title="TimePick API", version="1.2.0", description="실시간 가격 비교 & 구매 적기 추천 API", lifespan=lifespan)
    # 토큰은 Authorization 헤더로 보내므로 쿠키(credentials)는 허용하지 않는다. FRONTEND_URL의 출처는 settings.origins에 자동 포함
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_methods=CORS_METHODS, allow_headers=CORS_HEADERS,
                       allow_credentials=False, max_age=600)
    register_error_handlers(app)

    for r in (auth.router, products.router, ai.router, user_data.router, rpa.router, admin.router):
        app.include_router(r, prefix="/api/v1")

    @app.get("/health", tags=["운영"])
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "env": settings.app_env, "gemini": bool(settings.gemini_api_key)}

    # 화면 제공 방식은 실행 환경에 따라 하나만 선택된다.
    #   1) 프런트엔드 빌드 폴더가 있음(로컬 frontend/dist, 이전 통합 이미지) → 같은 도메인에서 화면 제공
    #   2) FRONTEND_URL 있음(Render 분리 배포: backend/Dockerfile)          → 화면 경로를 Static Site로 리다이렉트
    #   3) 둘 다 없음(EC2 api 컨테이너, 화면은 nginx 담당)                   → 루트에서 API 안내만 응답
    frontend_dir = Path(settings.frontend_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist")
    if frontend_dir.is_dir() and (frontend_dir / "index.html").is_file():
        _mount_frontend(app, frontend_dir)
    elif settings.frontend_url:
        _redirect_screens(app, settings)
    else:
        @app.get("/", include_in_schema=False)
        def root():
            return {"service": "TimePick API", "docs": "/docs", "health": "/health"}

    return app


app = create_app()

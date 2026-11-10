import logging
import secrets
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import oauth
from ..config import get_settings
from ..database import get_db
from ..errors import ApiError
from ..models import User
from ..schemas import DemoLoginIn, LoginIn, SignupIn, TokenOut, UserOut
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(tags=["인증"])
log = logging.getLogger(__name__)

# 시드(python -m app.seed)가 만드는 테스트 계정. 서비스 이름 변경(BuyTiming → PickTiming → TimePick) 전에 시드된 DB의 이전 이메일도 찾는다
DEMO_ACCOUNTS = {"user": ("demo@timepick.demo", "demo@picktiming.demo", "demo@buytiming.demo"),
                 "admin": ("admin@timepick.demo", "admin@picktiming.demo", "admin@buytiming.demo")}


def _token_out(user: User) -> TokenOut:
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.post("/auth/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise ApiError(409, "EMAIL_EXISTS", "이미 가입된 이메일입니다.")
    role = "ADMIN" if email in get_settings().admin_email_set else "USER"
    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip(), role=role)
    db.add(user)
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")
    return _token_out(user)


@router.get("/auth/providers")
def providers():
    """로그인 화면이 버튼 활성화 여부를 정하는 데 쓴다 (키 값은 노출하지 않음)"""
    s = get_settings()
    return {"demo_login": s.demo_login_enabled, **{p: oauth.enabled(s, p) for p in oauth.PROVIDERS}}


@router.post("/auth/demo-login", response_model=TokenOut)
def demo_login(body: DemoLoginIn, db: Session = Depends(get_db)):
    """테스트 계정 간편 로그인 (DEMO_LOGIN_ENABLED=true일 때만). 관리자 테스트 계정은 회원 권한을 바꿀 수 없다."""
    if not get_settings().demo_login_enabled:
        raise ApiError(403, "DEMO_LOGIN_DISABLED", "테스트 계정 로그인이 비활성화되어 있습니다.")
    emails = DEMO_ACCOUNTS[body.kind]
    users = {u.email: u for u in db.execute(select(User).where(User.email.in_(emails))).scalars()}
    user = next((users[e] for e in emails if e in users), None)
    if user is None:
        raise ApiError(404, "DEMO_ACCOUNT_MISSING", "테스트 계정이 없습니다. 서버에서 python -m app.seed를 실행해 주세요.")
    return _token_out(user)


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


# ---------------------------------------------------------------- 소셜 로그인(OAuth)
def _redirect_uri(request: Request, provider: str) -> str:
    base = get_settings().public_base_url.rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


def _check_provider(provider: str) -> None:
    if provider not in oauth.PROVIDERS:
        raise ApiError(404, "UNKNOWN_PROVIDER", "지원하지 않는 로그인 방식입니다.")
    if not oauth.enabled(get_settings(), provider):
        raise ApiError(503, "OAUTH_NOT_CONFIGURED", f"{provider} 로그인이 아직 설정되지 않았습니다.")


@router.get("/auth/oauth/{provider}/start", include_in_schema=False)
def oauth_start(provider: str, request: Request, next: str = Query("/", alias="next")):
    _check_provider(provider)
    s = get_settings()
    state = oauth.make_state(s, provider, oauth.safe_next(next))
    return RedirectResponse(oauth.authorize_url(s, provider, _redirect_uri(request, provider), state), status_code=302)


@router.get("/auth/oauth/{provider}/callback", include_in_schema=False)
def oauth_callback(provider: str, request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    _check_provider(provider)
    s = get_settings()
    try:
        if error or not code:
            raise ValueError(error or "로그인이 취소되었습니다.")
        next_path = oauth.read_state(s, state, provider)
        profile = oauth.fetch_profile(s, provider, code, state, _redirect_uri(request, provider))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        return RedirectResponse(s.frontend_link(f"/login?oauth_error={quote(str(exc)[:120])}"), status_code=302)
    except Exception:  # 제공자 서버 오류 등
        log.exception("oauth %s failed", provider)
        return RedirectResponse(s.frontend_link(f"/login?oauth_error={quote('소셜 로그인 처리 중 오류가 발생했습니다.')}"), status_code=302)

    email = profile["email"].lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        role = "ADMIN" if email in s.admin_email_set else "USER"
        # 소셜 계정은 비밀번호 로그인을 쓰지 않으므로 추측할 수 없는 무작위 비밀번호를 저장한다
        user = User(email=email, name=profile["name"][:50], role=role, password_hash=hash_password(secrets.token_urlsafe(24)))
        db.add(user)
        db.commit()
    token = create_token(user)
    # 토큰은 URL 조각(#)으로 전달해 서버 로그·Referer에 남지 않게 한다. 분리 배포면 FRONTEND_URL(화면 도메인)로 돌아간다
    return RedirectResponse(s.frontend_link(f"/oauth/callback#token={token}&next={quote(next_path)}"), status_code=302)

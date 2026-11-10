from datetime import datetime, time, timedelta

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings, now_local
from ..database import get_db
from ..errors import ApiError
from ..models import AiAdviceLog, ModelVersion, Product, RpaJobLog, User, Watchlist
from ..schemas import RoleIn
from ..security import admin_user

DEMO_ADMINS = {"admin@timepick.demo", "admin@picktiming.demo", "admin@buytiming.demo"}  # 이전 이름(BuyTiming·PickTiming)으로 시드된 테스트 관리자 포함

router = APIRouter(prefix="/admin", tags=["관리자"])


def _days(n: int) -> list:
    today = now_local().date()
    return [today - timedelta(days=i) for i in range(n - 1, -1, -1)]


@router.get("/rpa-logs")
def rpa_logs(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    since = datetime.combine(_days(7)[0], time.min)
    logs = db.execute(select(RpaJobLog).where(RpaJobLog.started_at >= since).order_by(RpaJobLog.started_at.desc())).scalars().all()
    collect = [l for l in logs if l.job_name == "collect_prices"]
    daily = []
    for d in _days(7):
        day = [l for l in collect if l.started_at.date() == d]
        daily.append({"date": d.isoformat(), "runs": len(day), "success": sum(l.collected for l in day),
                      "failed": sum(l.failed for l in day), "collected": sum(l.collected for l in day)})
    total = sum(r["collected"] + r["failed"] for r in daily)
    models = db.execute(select(ModelVersion).order_by(ModelVersion.id.desc()).limit(10)).scalars().all()
    return {
        "summary": {"runs_today": daily[-1]["runs"], "collected_today": daily[-1]["collected"],
                    "success_rate": round(1 - sum(r["failed"] for r in daily) / total, 4) if total else None,
                    "last_run_at": logs[0].started_at if logs else None},
        "daily": daily,
        "logs": [{"id": l.id, "job_name": l.job_name, "status": l.status, "collected": l.collected, "failed": l.failed,
                  "message": l.message, "started_at": l.started_at, "ended_at": l.ended_at} for l in logs[:50]],
        "models": [{"version": m.version, "algorithm": m.algorithm, "f1": m.f1, "precision": m.precision,
                    "trained_rows": m.trained_rows, "created_at": m.created_at, "active": m.is_active} for m in models],
    }


@router.get("/ai-metrics")
def ai_metrics(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    since = datetime.combine(_days(7)[0], time.min)
    rows = db.execute(select(AiAdviceLog, Product.name).join(Product, Product.id == AiAdviceLog.product_id)
                      .where(AiAdviceLog.created_at >= since).order_by(AiAdviceLog.id.desc())).all()
    logs = [r[0] for r in rows]
    daily = []
    for d in _days(7):
        day = [l for l in logs if l.created_at.date() == d]
        live = [l for l in day if not l.cache_hit]
        daily.append({"date": d.isoformat(), "calls": len(day), "cache_hits": sum(l.cache_hit for l in day),
                      "avg_latency_ms": round(sum(l.latency_ms for l in live) / len(live)) if live else 0,
                      "tokens": sum(l.input_tokens + l.output_tokens for l in day),
                      "validation_fail": sum(l.validation in ("FALLBACK", "ERROR") for l in day)})
    calls = len(logs)
    live = [l for l in logs if not l.cache_hit]
    return {
        "summary": {"calls_7d": calls, "avg_latency_ms": round(sum(l.latency_ms for l in live) / len(live)) if live else 0,
                    "tokens_7d": sum(l.input_tokens + l.output_tokens for l in logs),
                    "cache_hit_rate": round(sum(l.cache_hit for l in logs) / calls, 3) if calls else 0,
                    "validation_fail_rate": round(sum(l.validation in ("FALLBACK", "ERROR") for l in logs) / calls, 4) if calls else 0,
                    "model": get_settings().gemini_model + ("" if get_settings().gemini_api_key else " (키 미설정: 규칙 기반 대체)")},
        "daily": daily,
        "recent": [{"created_at": l.created_at, "type": l.type, "product": name, "latency_ms": l.latency_ms,
                    "cache_hit": l.cache_hit, "validation": l.validation} for l, name in rows[:20]],
    }


# ---------------------------------------------------------------- 회원 관리
def _user_view(u: User, watch_count: int = 0) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "created_at": u.created_at, "watch_count": watch_count}


@router.get("/users")
def list_users(q: str = Query("", max_length=100), role: str = Query("", pattern="^(|USER|ADMIN)$"),
               page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
               db: Session = Depends(get_db), _: User = Depends(admin_user)):
    """회원 목록: 이름·이메일 검색, 권한 필터, 페이지 나눔"""
    stmt = select(User)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.name.ilike(like)))
    if role:
        stmt = stmt.where(User.role == role)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    users = db.execute(stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size)).scalars().all()
    counts = dict(db.execute(select(Watchlist.user_id, func.count()).where(Watchlist.user_id.in_([u.id for u in users]))
                             .group_by(Watchlist.user_id)).all()) if users else {}
    admins = db.execute(select(func.count()).select_from(User).where(User.role == "ADMIN")).scalar_one()
    return {"items": [_user_view(u, counts.get(u.id, 0)) for u in users], "total": total, "page": page, "size": size,
            "summary": {"users": db.execute(select(func.count()).select_from(User)).scalar_one(), "admins": admins}}


@router.patch("/users/{user_id}/role")
def change_role(user_id: int, body: RoleIn, db: Session = Depends(get_db), actor: User = Depends(admin_user)):
    """회원 권한 변경(일반 사용자 ↔ 관리자)"""
    if actor.email in DEMO_ADMINS:
        raise ApiError(403, "DEMO_READ_ONLY", "테스트 관리자 계정은 회원 권한을 변경할 수 없습니다(조회만 가능).")
    target = db.get(User, user_id)
    if target is None:
        raise ApiError(404, "NOT_FOUND", "회원을 찾을 수 없습니다.")
    if target.id == actor.id:
        raise ApiError(400, "SELF_ROLE_CHANGE", "자기 자신의 권한은 변경할 수 없습니다.")
    if target.role == "ADMIN" and body.role == "USER":
        admins = db.execute(select(func.count()).select_from(User).where(User.role == "ADMIN")).scalar_one()
        if admins <= 1:
            raise ApiError(400, "LAST_ADMIN", "마지막 관리자는 일반 사용자로 바꿀 수 없습니다.")
    target.role = body.role
    db.commit()
    return _user_view(target)


# ---------------------------------------------------------------- 수동 수집(실제 관리자 전용)
COLLECT_COOLDOWN = timedelta(minutes=10)


def _collect_state(db: Session, user: User) -> dict:
    s = get_settings()
    last = db.execute(select(func.max(RpaJobLog.started_at)).where(RpaJobLog.job_name == "manual_collect")).scalar_one_or_none()
    allowed = user.email not in DEMO_ADMINS
    reason = "" if allowed else "테스트 관리자 계정은 조회만 가능합니다. 실제 관리자 계정으로 로그인해 주세요."
    return {"allowed": allowed, "configured": bool(s.github_dispatch_token), "reason": reason,
            "last_requested_at": last.isoformat() if last else None}


@router.get("/collect")
def collect_state(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    return _collect_state(db, user)


@router.post("/collect", status_code=202)
def trigger_collect(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    """GitHub Actions의 Collect 워크플로(job=collect)를 실행한다. 수집 자체는 Actions에서 돌고 결과는 수집 현황 로그에 남는다"""
    state = _collect_state(db, user)
    if not state["allowed"]:
        raise ApiError(403, "DEMO_READ_ONLY", state["reason"])
    s = get_settings()
    if not state["configured"]:
        raise ApiError(503, "COLLECT_NOT_CONFIGURED", "수동 수집이 설정되지 않았습니다. Render에 GITHUB_DISPATCH_TOKEN을 등록해 주세요.")
    if state["last_requested_at"] and now_local() - datetime.fromisoformat(state["last_requested_at"]) < COLLECT_COOLDOWN:
        raise ApiError(429, "COLLECT_TOO_SOON", "수동 수집은 10분에 한 번만 요청할 수 있습니다. 잠시 후 다시 시도해 주세요.")
    r = httpx.post(f"https://api.github.com/repos/{s.github_repo}/actions/workflows/collect-render.yml/dispatches",
                   json={"ref": "main", "inputs": {"job": "collect"}}, timeout=15,
                   headers={"Authorization": f"Bearer {s.github_dispatch_token}", "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28"})
    if r.status_code != 204:
        raise ApiError(502, "COLLECT_DISPATCH_FAILED", f"GitHub Actions 실행 요청에 실패했습니다(HTTP {r.status_code}). 토큰 권한을 확인해 주세요.")
    db.add(RpaJobLog(job_name="manual_collect", status="SUCCESS", message=f"수집 요청 접수({user.email}) · 결과는 이후 collect_prices 기록", started_at=now_local(), ended_at=now_local()))
    db.commit()
    return {"status": "REQUESTED", "message": "수집을 요청했습니다. 1~2분 뒤 수집 현황에서 결과를 확인하세요."}

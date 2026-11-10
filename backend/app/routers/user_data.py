"""관심 상품·알림·오늘의 할인 추천"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import ApiError, not_found
from ..models import Alert, Product, User, Watchlist
from ..schemas import ProductOut, WatchIn, WatchPatch
from ..security import current_user
from ..services.pricing import daily_lowest_all
from ..services.timing import cached_many, cached_or_analyze
from .products import get_product, has_active_listing

router = APIRouter(tags=["관심 상품·알림·추천"])


def watch_view(db: Session, w: Watchlist) -> dict:
    a = cached_or_analyze(db, w.product)
    cur = a["current_price"]
    return {"id": w.id, "product": ProductOut.model_validate(w.product), "target_price": w.target_price, "current_price": cur,
            "score": a["score"], "label": a["label"], "reached": cur is not None and w.target_price is not None and cur <= w.target_price,
            "created_at": w.created_at}


def _own(db: Session, user: User, watch_id: int) -> Watchlist:
    w = db.get(Watchlist, watch_id)
    if w is None or w.user_id != user.id:
        raise not_found("관심 상품")
    return w


@router.get("/watchlist")
def list_watch(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = db.execute(select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.id)).scalars().all()
    return {"items": [watch_view(db, w) for w in items]}


@router.post("/watchlist", status_code=201)
def add_watch(body: WatchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_product(db, body.product_id)
    w = Watchlist(user_id=user.id, product_id=body.product_id, target_price=body.target_price)
    db.add(w)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "ALREADY_WATCHING", "이미 관심 상품으로 등록되어 있습니다.") from None
    return watch_view(db, w)


@router.patch("/watchlist/{watch_id}")
def patch_watch(watch_id: int, body: WatchPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _own(db, user, watch_id)
    w.target_price, w.notified_at = body.target_price, None
    db.commit()
    return watch_view(db, w)


@router.delete("/watchlist/{watch_id}", status_code=204)
def delete_watch(watch_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_own(db, user, watch_id))
    db.commit()
    return Response(status_code=204)


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = db.execute(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id.desc()).limit(100)).scalars().all()
    return {"unread": sum(not a.is_read for a in items),
            "items": [{"id": a.id, "type": a.type, "product_id": a.product_id, "message": a.message, "is_read": a.is_read,
                       "created_at": a.created_at} for a in items]}


@router.post("/alerts/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    res = db.execute(update(Alert).where(Alert.user_id == user.id, Alert.is_read.is_(False)).values(is_read=True))
    db.commit()
    return {"updated": res.rowcount}


@router.get("/deals/today")
def deals_today(db: Session = Depends(get_db)):
    """홈 화면용 공개 데이터(개인 정보 없음): 로그인 없이 조회

    검색과 같이 활성 판매처가 있는 상품만 쓴다(비활성화한 시연 쇼핑몰 상품 제외). 적기 점수가 있는 상품(이력 30일 이상)이 6개보다 적으면
    가격이 수집된 인기 상품(priority 높은 순, 이미지 있는 것 먼저)을 '판단 보류'로 채워 빈 화면이 되지 않게 한다.
    """
    products = db.execute(select(Product).where(has_active_listing()).order_by(Product.id)).scalars().all()
    verdicts = cached_many(db, products, max_age_hours=25)
    analyzed = [(p, verdicts[p.id]) for p in products]
    timing = sorted([(p, a) for p, a in analyzed if a["score"] is not None], key=lambda x: -x[1]["score"])[:6]
    if len(timing) < 6:
        picked = {p.id for p, _ in timing}
        rest = sorted([(p, a) for p, a in analyzed if p.id not in picked and a["current_price"]],
                      key=lambda x: (not x[0].image_url, -x[0].priority, x[0].id))
        timing += rest[:6 - len(timing)]
    pv = daily_lowest_all(db, days=8)
    names = {p.id: p for p in products}
    drops = []
    for pid in pv.columns:
        col = pv[pid].dropna()
        if len(col) >= 8 and pid in names:
            drops.append({**ProductOut.model_validate(names[pid]).model_dump(), "current_price": int(col.iloc[-1]),
                          "change_7d": round(float(col.iloc[-1] / col.iloc[0] - 1), 4)})
    return {
        "timing": [{**ProductOut.model_validate(p).model_dump(), "current_price": a["current_price"], "score": a["score"], "label": a["label"]}
                   for p, a in timing],
        "drops": sorted(drops, key=lambda d: d["change_7d"])[:6],
    }

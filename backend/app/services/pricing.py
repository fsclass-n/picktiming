"""가격 이력 조회: 일별 최저 실구매가 시계열, 쇼핑몰별 비교"""
from datetime import timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import Mall, PriceHistory, ProductListing


def _day(col):
    return func.date(col)


def daily_lowest(db: Session, product_id: int, days: int | None = None) -> pd.Series:
    """상품의 일별 최저 실구매가(재고 있는 판매처 기준). index=날짜(Timestamp)"""
    q = (select(_day(PriceHistory.collected_at).label("d"), func.min(PriceHistory.total_price))
         .join(ProductListing, ProductListing.id == PriceHistory.listing_id)
         .where(ProductListing.product_id == product_id, PriceHistory.in_stock.is_(True))
         .group_by("d").order_by("d"))
    if days:
        q = q.where(PriceHistory.collected_at >= now_local() - timedelta(days=days))
    rows = db.execute(q).all()
    if not rows:
        return pd.Series(dtype="float64")
    return pd.Series([float(r[1]) for r in rows], index=pd.to_datetime([str(r[0]) for r in rows]))


def daily_lowest_all(db: Session, days: int) -> pd.DataFrame:
    """전체 상품의 최근 N일 일별 최저가 (행=날짜, 열=product_id)"""
    q = (select(ProductListing.product_id, _day(PriceHistory.collected_at).label("d"), func.min(PriceHistory.total_price))
         .join(ProductListing, ProductListing.id == PriceHistory.listing_id)
         .where(PriceHistory.in_stock.is_(True), PriceHistory.collected_at >= now_local() - timedelta(days=days))
         .group_by(ProductListing.product_id, "d"))
    rows = db.execute(q).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["product_id", "d", "price"])
    df["d"] = pd.to_datetime(df["d"].astype(str))
    return df.pivot(index="d", columns="product_id", values="price").sort_index()


def compare(db: Session, product_id: int) -> dict:
    """판매처별 최신 수집 가격과 최저 실구매가"""
    latest = (select(PriceHistory.listing_id, func.max(PriceHistory.collected_at).label("t"))
              .join(ProductListing, ProductListing.id == PriceHistory.listing_id)
              .where(ProductListing.product_id == product_id).group_by(PriceHistory.listing_id).subquery())
    rows = db.execute(
        select(PriceHistory, ProductListing, Mall)
        .join(latest, (latest.c.listing_id == PriceHistory.listing_id) & (latest.c.t == PriceHistory.collected_at))
        .join(ProductListing, ProductListing.id == PriceHistory.listing_id)
        .join(Mall, Mall.id == ProductListing.mall_id)
        .where(ProductListing.is_active.is_(True))
    ).all()
    in_stock = [ph.total_price for ph, _, _ in rows if ph.in_stock]
    lowest = min(in_stock) if in_stock else None
    items = [{
        "mall_id": mall.id, "mall": mall.name, "mall_kind": mall.kind or "compare", "price": ph.price, "shipping_fee": ph.shipping_fee,
        "total_price": ph.total_price, "in_stock": ph.in_stock, "is_lowest": ph.in_stock and ph.total_price == lowest,
        "url": listing.url, "offer_count": listing.offer_count, "high_price": listing.high_price,
        "rating": listing.rating, "review_count": listing.review_count,
    } for ph, listing, mall in rows]
    items.sort(key=lambda i: (not i["in_stock"], i["total_price"]))
    collected = max((ph.collected_at for ph, _, _ in rows), default=None)
    return {"product_id": product_id, "collected_at": collected, "lowest_total": lowest, "items": items}


def price_chart(db: Session, product_id: int, days: int) -> dict:
    """가격 추이 차트용: 쇼핑몰별 일별 실구매가 + 최저가 + 역대 최저가"""
    since = now_local() - timedelta(days=days)
    rows = db.execute(
        select(Mall.name, _day(PriceHistory.collected_at).label("d"), func.min(PriceHistory.total_price))
        .join(ProductListing, ProductListing.id == PriceHistory.listing_id)
        .join(Mall, Mall.id == ProductListing.mall_id)
        .where(ProductListing.product_id == product_id, PriceHistory.in_stock.is_(True), PriceHistory.collected_at >= since)
        .group_by(Mall.name, "d")
    ).all()
    all_time = daily_lowest(db, product_id)
    atm = {"price": int(all_time.min()), "date": all_time.idxmin().date().isoformat()} if len(all_time) else {"price": None, "date": None}
    if not rows:
        return {"days": days, "dates": [], "malls": [], "lowest": [], "all_time_min": atm}
    df = pd.DataFrame(rows, columns=["mall", "d", "price"])
    df["d"] = pd.to_datetime(df["d"].astype(str)).dt.date.astype(str)
    pv = df.pivot(index="d", columns="mall", values="price").sort_index()
    clean = lambda col: [None if pd.isna(v) else int(v) for v in col]  # noqa: E731
    return {
        "days": days, "dates": list(pv.index),
        "malls": [{"mall": m, "values": clean(pv[m])} for m in sorted(pv.columns)],
        "lowest": clean(pv.min(axis=1)), "all_time_min": atm,
    }

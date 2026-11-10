"""구매 적기 판정: 피처 → 하락 확률(모델 또는 규칙) → 적기 점수·판정"""
from datetime import timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import now_local
from ..ml.features import FEATURES, MIN_HISTORY, drop_events, feature_frame, heuristic_prob
from ..ml.model_store import load_active
from ..models import Product, TimingPrediction
from .pricing import daily_lowest

VERDICT = {"BUY_NOW": "지금 구매 추천", "WAIT_A_BIT": "조금 더 지켜보기", "WAIT": "기다리기 권장", "HOLD": "판단 보류"}


def label_for(score: int | None) -> str:
    if score is None:
        return "HOLD"
    return "BUY_NOW" if score >= 70 else "WAIT_A_BIT" if score >= 40 else "WAIT"


def analyze(db: Session, product: Product) -> dict:
    s = daily_lowest(db, product.id)
    n = len(s)
    base = {"product_id": product.id, "history_days": n, "model_version": None, "current_price": None, "min_90d": None,
            "avg_90d": None, "min_90d_date": None, "percentile_90d": None, "prob_drop_7d": None, "score": None, "label": "HOLD",
            "trend_30d_pct": None, "days_since_drop": None, "discount_cycle_days": None}
    if n == 0:
        return base
    w = s.iloc[-90:]
    base.update(current_price=int(s.iloc[-1]), min_90d=int(w.min()), avg_90d=int(round(w.mean())),
                min_90d_date=w.idxmin().date().isoformat())
    if n < MIN_HISTORY:
        return base
    row = feature_frame(s).iloc[-1]
    model, mv = load_active(db)
    if model is not None:
        prob = float(model.predict_proba(pd.DataFrame([row[FEATURES]]))[0, 1])
        version = mv.version
    else:
        prob, version = heuristic_prob(row), "heuristic"
    pct = float(row["percentile_90d"])
    score = int(round((1 - prob) * 70 + (1 - pct) * 30))
    events = drop_events(s)
    cycle = int(round((events[-1] - events[0]).days / (len(events) - 1))) if len(events) > 1 else None
    base.update(model_version=version, percentile_90d=round(pct, 3), prob_drop_7d=round(prob, 3), score=score,
                label=label_for(score), trend_30d_pct=round(float(row["slope_30d"]), 3),
                days_since_drop=int(row["days_since_drop"]), discount_cycle_days=cycle, _model_version_id=mv.id if mv else None)
    return base


def save_prediction(db: Session, a: dict) -> TimingPrediction:
    tp = TimingPrediction(product_id=a["product_id"], model_version_id=a.get("_model_version_id"), current_price=a["current_price"],
                          min_90d=a["min_90d"], percentile_90d=a["percentile_90d"], prob_drop_7d=a["prob_drop_7d"],
                          score=a["score"], label=a["label"], history_days=a["history_days"])
    db.add(tp)
    return tp


def latest_prediction(db: Session, product_id: int) -> TimingPrediction | None:
    return db.execute(select(TimingPrediction).where(TimingPrediction.product_id == product_id)
                      .order_by(TimingPrediction.id.desc()).limit(1)).scalar_one_or_none()


def cached_or_analyze(db: Session, product: Product, max_age_hours: int = 2) -> dict:
    """최근 판정이 있으면 그대로 쓰고(가격 등록 직후 사전 계산), 없으면 계산 후 저장"""
    tp = latest_prediction(db, product.id)
    if tp and tp.created_at >= now_local() - timedelta(hours=max_age_hours):
        return {"product_id": product.id, "current_price": tp.current_price, "score": tp.score, "label": tp.label}
    a = analyze(db, product)
    save_prediction(db, a)
    db.commit()
    return a


def cached_many(db: Session, products: list[Product], max_age_hours: int = 2) -> dict[int, dict]:
    """여러 상품의 판정을 한 번에: 최신 판정을 쿼리 1번으로 읽고, 없거나 오래된 상품만 계산한다(상품 수백 개 검색용)"""
    ids = [p.id for p in products]
    latest = select(func.max(TimingPrediction.id)).where(TimingPrediction.product_id.in_(ids)).group_by(TimingPrediction.product_id)
    found = {tp.product_id: tp for tp in db.execute(select(TimingPrediction).where(TimingPrediction.id.in_(latest))).scalars()} if ids else {}
    since = now_local() - timedelta(hours=max_age_hours)
    out = {}
    for p in products:
        tp = found.get(p.id)
        out[p.id] = ({"product_id": p.id, "current_price": tp.current_price, "score": tp.score, "label": tp.label}
                     if tp and tp.created_at >= since else cached_or_analyze(db, p, max_age_hours))
    return out


def public_view(a: dict) -> dict:
    return {k: v for k, v in a.items() if not k.startswith("_")}

"""개발·시연용 초기 데이터: 쇼핑몰 3곳, 상품 12종, 가격 이력 120일, 데모 계정, 초기 모델 학습

실행: python -m app.seed            (데이터가 이미 있으면 건너뜀)
      python -m app.seed --reset    (개발 DB 전체 삭제 후 재생성 — 운영 DB에서 사용 금지)
계정 비밀번호는 환경 변수 SEED_DEMO_PASSWORD / SEED_ADMIN_PASSWORD, 없으면 무작위 생성 후 출력한다.
"""
import argparse
import os
import secrets
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import func, select

from .config import get_settings, now_local
from .database import Base, SessionLocal, engine, init_db
from .ml.train import train_and_register
from .models import Mall, PriceHistory, Product, ProductListing, RpaJobLog, User, Watchlist
from .security import hash_password
from .services.timing import analyze, save_prediction

MALLS = [("쇼핑몰 A", "https://mall-a.example.com", 0.0, lambda p: 0),
         ("쇼핑몰 B", "https://mall-b.example.com", -0.016, lambda p: 3000),
         ("쇼핑몰 C", "https://mall-c.example.com", 0.035, lambda p: 0 if p >= 30000 else 2500)]

PRODUCTS = [  # name, brand, model_no, category, base, days, phase
    ("무선 이어폰 X2", "SoundOne", "X2-ANC", "디지털", 139000, 120, "sale"),
    ("노이즈캔슬링 헤드폰 H7", "SoundOne", "H7", "디지털", 329000, 120, "before"),
    ("14인치 노트북 Air", "Bitbook", "BA14-2026", "디지털", 1190000, 120, None),
    ("스마트워치 S5", "Tickr", "S5-44", "디지털", 259000, 21, None),
    ("로봇청소기 R9", "CleanBot", "R9", "가전", 489000, 120, None),
    ("에어프라이어 5.5L", "Kitchy", "AF55", "가전", 99000, 120, "sale"),
    ("무선 청소기 V8", "CleanBot", "V8", "가전", 359000, 120, "before"),
    ("생수 2L × 12", "맑은샘", "W2L12", "생필품", 8900, 120, None),
    ("세탁세제 3L", "하얀빨래", "LD3L", "생필품", 15900, 120, "sale"),
    ("화장지 30롤", "부드러움", "TP30", "생필품", 21900, 120, None),
    ("분유 800g × 3", "튼튼", "MF800-3", "유아", 89000, 120, None),
    ("기저귀 대형 4팩", "뽀송", "DP-L4", "유아", 72000, 120, "before"),
]


def _round(v: float, base: int) -> int:
    return int(round(v / 100) * 100) if base >= 100000 else int(round(v / 10) * 10)


def gen_prices(idx: int, base: int, days: int, phase_kind: str | None, today: datetime):
    """할인 주기·추세·잡음을 가진 일별 가격 (쇼핑몰별 가격·배송비·재고)"""
    rng = np.random.default_rng(1000 + idx)
    period = int(24 + rng.integers(0, 10))
    phase = int(rng.integers(0, period))
    if phase_kind == "sale":
        phase = (period - ((days - 2) % period)) % period
    elif phase_kind == "before":
        phase = (period - ((days + 2) % period)) % period
    trend = (rng.random() - 0.45) * 0.1
    drift = 0.0
    for k in range(days):
        day = today - timedelta(days=days - 1 - k)
        drift = drift * 0.85 + (rng.random() - 0.5) * 0.012
        on_sale = (k + phase) % period < 4
        f = 1 + trend * k / max(days - 1, 1) + drift + ((-0.1 - rng.random() * 0.04) if on_sale else 0) + (-0.015 if day.day >= 26 else 0)
        for m, (_, _, offset, ship) in enumerate(MALLS):
            price = _round(base * (f + offset + (rng.random() - 0.5) * 0.012), base)
            yield day, m, price, ship(price)


def seed(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as db:
        if db.execute(select(func.count()).select_from(Product)).scalar_one():
            print("이미 데이터가 있어 시드를 건너뜁니다. (--reset으로 재생성)")
            return
        malls = [Mall(name=n, base_url=u, robots_checked_at=now_local().date()) for n, u, _, _ in MALLS]
        db.add_all(malls)
        db.flush()
        today = now_local().replace(hour=12, minute=0, second=0, microsecond=0)
        if now_local() < today:
            today -= timedelta(days=1)
        for idx, (name, brand, model_no, cat, base, days, phase) in enumerate(PRODUCTS, start=1):
            p = Product(name=name, brand=brand, model_no=model_no, category=cat)
            db.add(p)
            db.flush()
            listings = [ProductListing(product_id=p.id, mall_id=m.id, url=f"{m.base_url}/products/{model_no}") for m in malls]
            db.add_all(listings)
            db.flush()
            for day, m, price, ship in gen_prices(idx, base, days, phase, today):
                sold_out = model_no == "V8" and m == 2 and day >= today - timedelta(days=1)
                db.add(PriceHistory(listing_id=listings[m].id, price=price, shipping_fee=ship, total_price=price + ship,
                                    in_stock=not sold_out, collected_at=day))
        for k in range(120):
            day = today - timedelta(days=119 - k)
            db.add(RpaJobLog(job_name="collect_prices", status="SUCCESS", collected=len(PRODUCTS) * 3, failed=0,
                             message="seed", started_at=day, ended_at=day + timedelta(seconds=40)))

        pw = {}
        admins = get_settings().admin_email_set
        for email, name, env in (("demo@timepick.demo", "데모 사용자", "SEED_DEMO_PASSWORD"),
                                 ("admin@timepick.demo", "관리자", "SEED_ADMIN_PASSWORD")):
            pw[email] = os.getenv(env) or secrets.token_urlsafe(9)
            role = "ADMIN" if email.startswith("admin") or email in admins else "USER"
            db.add(User(email=email, name=name, role=role, password_hash=hash_password(pw[email])))
        db.commit()

        demo = db.execute(select(User).where(User.email == "demo@timepick.demo")).scalar_one()
        targets = {"X2-ANC": 130000, "AF55": 85000, "MF800-3": 80000}
        for p in db.execute(select(Product).where(Product.model_no.in_(targets))).scalars():
            db.add(Watchlist(user_id=demo.id, product_id=p.id, target_price=targets[p.model_no]))
        db.commit()

        print("모델 학습:", train_and_register(db, force=True))
        for p in db.execute(select(Product)).scalars():
            save_prediction(db, analyze(db, p))
        db.commit()
        print("시드 완료. 데모 계정:")
        for email, secret in pw.items():
            print(f"  {email} / {secret}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="개발 DB의 모든 테이블을 삭제 후 재생성")
    seed(ap.parse_args().reset)

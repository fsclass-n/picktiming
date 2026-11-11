"""RPA 수신 API (X-RPA-KEY 인증) — 수집기·스케줄러 전용"""
import base64
import logging
from datetime import timedelta
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import get_settings, now_local
from ..database import SessionLocal, get_db
from ..errors import ApiError
from ..jobs.weekly_report import build_report
from ..ml.train import train_and_register
from ..models import Mall, ModelVersion, PriceHistory, Product, ProductListing, PublicPrice, RpaJobLog
from ..schemas import CatalogIn, EnsureListingsIn, JobLogIn, ModelUploadIn, PriceBulkIn, PublicPriceIn
from ..security import rpa_key
from ..services.alerts import refresh_product

router = APIRouter(prefix="/rpa", tags=["RPA"], dependencies=[Depends(rpa_key)])
log = logging.getLogger(__name__)


@router.get("/listings")
def listings(db: Session = Depends(get_db)):
    """수집 대상 판매 페이지 목록 (활성 쇼핑몰·활성 판매처)"""
    latest = (select(PriceHistory.listing_id, func.max(PriceHistory.id).label("pid")).group_by(PriceHistory.listing_id).subquery())
    rows = db.execute(select(ProductListing, Product, Mall, PriceHistory)
                      .join(Product, Product.id == ProductListing.product_id).join(Mall, Mall.id == ProductListing.mall_id)
                      .outerjoin(latest, latest.c.listing_id == ProductListing.id)
                      .outerjoin(PriceHistory, PriceHistory.id == latest.c.pid)
                      .where(ProductListing.is_active.is_(True), Mall.is_active.is_(True))
                      .order_by(Product.priority.desc(), Product.id, ProductListing.id)).all()  # 우선순위 높은 상품부터
    return {"items": [{"listing_id": l.id, "product_id": p.id, "model_no": p.model_no, "product": p.name, "priority": p.priority,
                       "mall_id": m.id, "mall": m.name, "url": l.url,
                       "last_price": ph.price if ph else None, "last_shipping_fee": ph.shipping_fee if ph else None}
                      for l, p, m, ph in rows]}


@router.post("/prices/bulk")
def prices_bulk(body: PriceBulkIn, db: Session = Depends(get_db)):
    """가격 일괄 등록 → 판정 갱신(사전 계산) → 목표가·판정 변경 알림

    같은 판매처에 같은 시간대(정시~59분) 가격이 이미 있으면 건너뛴다.
    EC2 수집기와 GitHub Actions(Render용) 수집기가 같은 DB에 보내도 중복 저장되지 않는다.
    """
    at = body.collected_at or now_local()
    if at.tzinfo is not None:
        at = at.astimezone(ZoneInfo(get_settings().tz)).replace(tzinfo=None)
    ids = [i.listing_id for i in body.items]
    listings = {l.id: l for l in db.execute(select(ProductListing).where(ProductListing.id.in_(ids))).scalars()}
    valid = {lid: l.product_id for lid, l in listings.items()}
    for i in body.items:  # 판매처 수·최고가·평점·사양 요약: 값이 온 것만 최신 값으로 덮어쓴다(같은 시간대 중복 가격이어도 갱신)
        if (l := listings.get(i.listing_id)) is None:
            continue
        for key in ("offer_count", "high_price", "rating", "review_count"):
            if (value := getattr(i, key)) is not None:
                setattr(l, key, value)
        if i.spec and l.product.spec_summary != i.spec:
            l.product.spec_summary = i.spec
    hour = at.replace(minute=0, second=0, microsecond=0)
    seen = set(db.execute(select(PriceHistory.listing_id).where(
        PriceHistory.listing_id.in_(ids), PriceHistory.collected_at >= hour, PriceHistory.collected_at < hour + timedelta(hours=1))).scalars())
    touched: set[int] = set()
    inserted = duplicate = 0
    for i in body.items:
        if i.listing_id not in valid:
            continue
        if i.listing_id in seen:
            duplicate += 1
            continue
        seen.add(i.listing_id)
        db.add(PriceHistory(listing_id=i.listing_id, price=i.price, shipping_fee=i.shipping_fee,
                            total_price=i.price + i.shipping_fee, in_stock=i.in_stock, collected_at=at))
        touched.add(valid[i.listing_id])
        inserted += 1
    db.flush()
    alerts = sum(refresh_product(db, db.get(Product, pid)) for pid in touched)
    db.commit()
    return {"inserted": inserted, "skipped": sum(i.listing_id not in valid for i in body.items), "duplicate": duplicate,
            "products_updated": len(touched), "alerts_created": alerts}


@router.put("/public-prices")
def public_prices(body: PublicPriceIn, db: Session = Depends(get_db)):
    by_model = {p.model_no: p.id for p in db.execute(select(Product)).scalars()}
    saved = 0
    for i in body.items:
        pid = by_model.get(i.model_no)
        if pid is None:
            continue
        row = db.execute(select(PublicPrice).where(PublicPrice.product_id == pid, PublicPrice.good_id == i.good_id,
                                                   PublicPrice.survey_date == i.survey_date)).scalar_one_or_none()
        if row:
            row.price, row.store_type = i.price, i.store_type
        else:
            db.add(PublicPrice(product_id=pid, good_id=i.good_id, price=i.price, store_type=i.store_type, survey_date=i.survey_date))
        saved += 1
    db.commit()
    return {"saved": saved, "unmatched": len(body.items) - saved}


@router.post("/models", status_code=201)
def upload_model(body: ModelUploadIn, db: Session = Depends(get_db)):
    try:
        artifact = base64.b64decode(body.artifact_b64, validate=True)
    except ValueError:
        raise ApiError(400, "INVALID_ARTIFACT", "artifact_b64가 올바른 base64 형식이 아닙니다.") from None
    if body.activate:
        db.execute(update(ModelVersion).values(is_active=False))
    mv = ModelVersion(version=body.version, algorithm=body.algorithm, f1=body.f1, precision=body.precision,
                      trained_rows=body.trained_rows, artifact=artifact, is_active=body.activate)
    db.add(mv)
    db.commit()
    return {"id": mv.id, "version": mv.version, "active": mv.is_active}


@router.post("/logs", status_code=201)
def job_log(body: JobLogIn, db: Session = Depends(get_db)):
    row = RpaJobLog(**body.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id}


def _train_job() -> None:
    with SessionLocal() as db:
        try:
            log.info("train result: %s", train_and_register(db))
        except Exception as exc:  # 학습 실패는 로그로 남기고 API는 계속 동작
            log.exception("train failed")
            db.rollback()
            db.add(RpaJobLog(job_name="train_model", status="FAIL", message=str(exc)[:500], started_at=now_local(), ended_at=now_local()))
            db.commit()


@router.post("/train", status_code=202)
def train(background: BackgroundTasks):
    """모델 재학습을 백그라운드로 실행 (스케줄러가 매일 03:00 호출)"""
    background.add_task(_train_job)
    return {"status": "ACCEPTED"}


@router.get("/reports/weekly")
def weekly_report(db: Session = Depends(get_db)):
    data, name = build_report(db)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/ensure-listings")
def ensure_listings(body: EnsureListingsIn, db: Session = Depends(get_db)):
    """API 기반 판매처(예: 네이버쇼핑 OpenAPI)를 모든 상품에 연결한다. 이미 있으면 건너뜀(여러 번 호출해도 안전)"""
    mall = db.execute(select(Mall).where(Mall.name == body.name)).scalar_one_or_none()
    if mall is None:
        mall = Mall(name=body.name, base_url=body.base_url, robots_checked_at=now_local().date())
        db.add(mall)
        db.flush()
    have = set(db.execute(select(ProductListing.product_id).where(ProductListing.mall_id == mall.id)).scalars())
    created = 0
    for p in db.execute(select(Product)).scalars():
        if p.id in have:
            continue
        query = " ".join(x for x in (p.name, p.brand if p.brand != "-" else "") if x)
        db.add(ProductListing(product_id=p.id, mall_id=mall.id, url=body.url_template.format(query=quote(query))))
        created += 1
    db.commit()
    return {"mall_id": mall.id, "created": created}


@router.put("/catalog")
def sync_catalog(body: CatalogIn, db: Session = Depends(get_db), hash: str = Query("", max_length=64, pattern=r"^[0-9a-f]*$")):
    """실제 수집 대상(rpa/catalog.json)을 DB에 맞춘다. 여러 번 호출해도 결과가 같다(수집 작업이 매번 먼저 호출).

    - 쇼핑몰: 이름으로 찾아 만들거나 주소·활성 상태를 갱신
    - 상품: model_no로 찾아 만들거나 이름·브랜드·분류를 갱신 / 판매처: (상품, 쇼핑몰)마다 하나, 주소가 바뀌면 갱신
    - retire_mall_hosts: 더 이상 수집하지 않는 쇼핑몰을 삭제 없이 비활성화 → 수집 대상·검색 결과에서 빠짐(가격 이력은 보존)
    """
    hosts = {m.name: urlparse(m.base_url).netloc for m in body.malls}
    for p in body.products:  # 먼저 전부 검증해 일부만 반영되는 일이 없게 한다
        for item in p.listings:
            if item.mall not in hosts:
                raise ApiError(400, "UNKNOWN_MALL", f"카탈로그 malls에 없는 쇼핑몰입니다: {item.mall}")
            if urlparse(item.url).netloc != hosts[item.mall]:
                raise ApiError(400, "LISTING_DOMAIN_MISMATCH", f"{item.mall} 판매처 주소는 {hosts[item.mall]} 도메인이어야 합니다: {item.url}")

    today = now_local().date()
    malls: dict[str, Mall] = {}
    for m in body.malls:
        mall = db.execute(select(Mall).where(Mall.name == m.name)).scalars().first()
        if mall is None:
            mall = Mall(name=m.name, base_url=m.base_url)
            db.add(mall)
        mall.base_url, mall.is_active, mall.robots_checked_at = m.base_url, True, today
        malls[m.name] = mall
    db.flush()

    stats = {"products_created": 0, "products_updated": 0, "listings_created": 0, "listings_updated": 0}
    # 상품 수백 개를 매 수집마다 맞추므로 기존 상품·판매처를 쿼리 2번으로 미리 읽는다(Render ↔ TiDB 왕복 수 최소화)
    existing: dict[str, Product] = {}
    for prod in db.execute(select(Product).where(Product.model_no.in_([p.model_no for p in body.products])).order_by(Product.id.desc())).scalars():
        existing[prod.model_no] = prod  # 같은 model_no가 여럿이면 가장 먼저 만든 상품(id가 작은 것)
    have = {(l.product_id, l.mall_id): l for l in db.execute(
        select(ProductListing).where(ProductListing.product_id.in_([prod.id for prod in existing.values()]))).scalars()} if existing else {}
    for p in body.products:
        product = existing.get(p.model_no)
        if product is None:
            product = Product(model_no=p.model_no, name=p.name, brand=p.brand, category=p.category, priority=p.priority, image_url=p.image_url)
            db.add(product)
            db.flush()
            existing[p.model_no] = product
            stats["products_created"] += 1
        elif (product.name, product.brand, product.category, product.priority, product.image_url) != (p.name, p.brand, p.category, p.priority, p.image_url):
            product.name, product.brand, product.category, product.priority, product.image_url = p.name, p.brand, p.category, p.priority, p.image_url
            stats["products_updated"] += 1
        for item in p.listings:
            mall = malls[item.mall]
            listing = have.get((product.id, mall.id))
            if listing is None:
                have[(product.id, mall.id)] = listing = ProductListing(product_id=product.id, mall_id=mall.id, url=item.url)
                db.add(listing)
                stats["listings_created"] += 1
            elif listing.url != item.url or not listing.is_active:
                listing.url, listing.is_active = item.url, True
                stats["listings_updated"] += 1

    keep = set(hosts.values())
    retire = {h.strip().lower() for h in body.retire_mall_hosts if h.strip()} - keep
    retired = 0
    for mall in db.execute(select(Mall).where(Mall.is_active.is_(True))).scalars():
        if urlparse(mall.base_url).netloc.lower() in retire:
            mall.is_active = False
            retired += 1
    if hash:  # 수집기가 보낸 catalog.json 해시를 남긴다 → 다음 수집에서 내용이 같으면 동기화를 건너뛴다(GET /rpa/status)
        db.add(RpaJobLog(job_name="sync_catalog", status="SUCCESS", collected=len(body.products), message=f"hash={hash}",
                         started_at=now_local(), ended_at=now_local()))
    db.commit()
    return {"malls": len(malls), **stats, "malls_retired": retired}


@router.get("/status")
def collect_status(db: Session = Depends(get_db)):
    """마지막으로 성공(또는 일부 성공)한 가격 수집 시각. 수집기가 이번 6시간 구간에 이미 수집했는지 판단할 때 쓴다"""
    last = db.execute(select(func.max(RpaJobLog.started_at)).where(
        RpaJobLog.job_name == "collect_prices", RpaJobLog.status.in_(("SUCCESS", "PARTIAL")))).scalar_one_or_none()
    sync = db.execute(select(RpaJobLog).where(RpaJobLog.job_name == "sync_catalog").order_by(RpaJobLog.id.desc()).limit(1)).scalar_one_or_none()
    return {"last_collect_at": last.isoformat() if last else None,
            "catalog_hash": (sync.message or "").removeprefix("hash=") if sync else None,
            "catalog_synced_at": sync.started_at.isoformat() if sync else None}

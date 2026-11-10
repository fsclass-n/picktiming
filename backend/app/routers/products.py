from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import ApiError
from ..models import Mall, Product, ProductListing, PublicPrice, User
from ..schemas import OfflinePriceOut, ProductDetailOut, ProductOut, ProductRegisterIn, ProductSearchItem
from ..security import current_user
from ..services import pricing
from ..services.timing import cached_many

router = APIRouter(tags=["상품·가격 비교"])


def get_product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise ApiError(404, "PRODUCT_NOT_FOUND", "상품을 찾을 수 없습니다.")
    return p


def has_active_listing():
    """활성 쇼핑몰의 활성 판매처가 하나라도 있는 상품만 노출한다(비활성화한 시연용 쇼핑몰 상품은 숨김, 데이터는 보존)"""
    return (select(ProductListing.id).join(Mall, Mall.id == ProductListing.mall_id)
            .where(ProductListing.product_id == Product.id, ProductListing.is_active.is_(True), Mall.is_active.is_(True)).exists())


SEARCH_SORTS = {
    "id": lambda i: i.id,
    "score": lambda i: (-(i.score if i.score is not None else -1), i.id),
    "price": lambda i: (i.lowest_price is None, i.lowest_price or 0, i.id),
}


@router.get("/products/search")
def search(q: str = Query("", max_length=100), category: str = Query("", max_length=200, description="분류(쉼표로 여러 개)"),
           buy_only: bool = False, sort: str = Query("id", pattern="^(id|score|price)$"),
           page: int = Query(1, ge=1, le=1000), size: int = Query(50, ge=1, le=100),
           db: Session = Depends(get_db), _: User = Depends(current_user)):
    """상품 검색. 판정 점수·가격 정렬과 '지금 구매' 필터가 있어 전체를 판정한 뒤 page 단위로 잘라 준다(total = 조건에 맞는 전체 수)"""
    stmt = select(Product).where(has_active_listing()).order_by(Product.id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.brand.ilike(like), Product.category.ilike(like), Product.model_no.ilike(like)))
    if cats := [c.strip() for c in category.split(",") if c.strip()]:
        stmt = stmt.where(Product.category.in_(cats))
    products = list(db.execute(stmt).scalars())
    verdicts = cached_many(db, products, max_age_hours=25)  # 판정은 가격 수집 때 미리 계산된다(하위 상품은 하루 1회) → 목록은 그 결과를 재사용
    items = [ProductSearchItem(**ProductOut.model_validate(p).model_dump(), lowest_price=verdicts[p.id]["current_price"],
                               score=verdicts[p.id]["score"], label=verdicts[p.id]["label"]) for p in products]
    if buy_only:
        items = [i for i in items if i.label == "BUY_NOW"]
    items.sort(key=SEARCH_SORTS[sort])
    return {"items": items[(page - 1) * size:page * size], "total": len(items), "page": page, "size": size}


@router.post("/products", status_code=201)
def register(body: ProductRegisterIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """상품 URL 등록: 등록된 쇼핑몰 도메인만 허용하고, 다음 수집 주기부터 가격을 반영한다."""
    host = urlparse(body.url).netloc.lower()
    malls = db.execute(select(Mall).where(Mall.is_active.is_(True))).scalars().all()
    mall = next((m for m in malls if urlparse(m.base_url).netloc.lower() == host), None)
    if mall is None:
        names = ", ".join(m.name for m in malls) or "없음"
        raise ApiError(400, "UNSUPPORTED_MALL", f"수집이 허용된 쇼핑몰의 상품 URL만 등록할 수 있습니다. (지원: {names})")
    existing = db.execute(select(ProductListing).where(ProductListing.url == body.url)).scalar_one_or_none()
    if existing:
        return {"product": ProductOut.model_validate(existing.product), "status": "EXISTS", "message": "이미 등록된 상품입니다."}
    product = Product(name=(body.name or "등록 상품").strip())
    db.add(product)
    db.flush()
    db.add(ProductListing(product_id=product.id, mall_id=mall.id, url=body.url))
    db.commit()
    return {"product": ProductOut.model_validate(product), "status": "PENDING", "message": "다음 수집 주기(하루 4회: 0·6·12·18시)부터 가격이 반영됩니다."}


@router.get("/products/{product_id}", response_model=ProductDetailOut)
def detail(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = get_product(db, product_id)
    cnt = db.execute(select(func.count()).select_from(ProductListing)
                     .where(ProductListing.product_id == p.id, ProductListing.is_active.is_(True))).scalar_one()
    # 참가격(오프라인 판매점 조사가): 가장 최근 조사일의 최저가. 매핑된 상품(rpa/public_price_map.json)만 있다
    offline = db.execute(select(PublicPrice).where(PublicPrice.product_id == p.id)
                         .order_by(PublicPrice.survey_date.desc(), PublicPrice.price).limit(1)).scalar_one_or_none()
    return ProductDetailOut(**ProductOut.model_validate(p).model_dump(), listings_count=cnt, spec_summary=p.spec_summary,
                            offline_price=OfflinePriceOut(price=offline.price, store_type=offline.store_type, survey_date=offline.survey_date) if offline else None)


@router.get("/products/{product_id}/compare")
def compare(product_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    get_product(db, product_id)
    return pricing.compare(db, product_id)


@router.get("/products/{product_id}/prices")
def prices(product_id: int, days: int = Query(90), db: Session = Depends(get_db), _: User = Depends(current_user)):
    if days not in (7, 30, 90):
        raise ApiError(400, "INVALID_DAYS", "days는 7, 30, 90 중 하나여야 합니다.")
    get_product(db, product_id)
    return pricing.price_chart(db, product_id, days)

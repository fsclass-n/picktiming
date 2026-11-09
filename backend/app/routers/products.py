from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import ApiError
from ..models import Mall, Product, ProductListing, User
from ..schemas import ProductDetailOut, ProductOut, ProductRegisterIn, ProductSearchItem
from ..security import current_user
from ..services import pricing
from ..services.timing import cached_or_analyze

router = APIRouter(tags=["상품·가격 비교"])


def get_product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise ApiError(404, "PRODUCT_NOT_FOUND", "상품을 찾을 수 없습니다.")
    return p


def _has_active_listing():
    """활성 쇼핑몰의 활성 판매처가 하나라도 있는 상품만 노출한다(비활성화한 시연용 쇼핑몰 상품은 숨김, 데이터는 보존)"""
    return (select(ProductListing.id).join(Mall, Mall.id == ProductListing.mall_id)
            .where(ProductListing.product_id == Product.id, ProductListing.is_active.is_(True), Mall.is_active.is_(True)).exists())


@router.get("/products/search")
def search(q: str = Query("", max_length=100), db: Session = Depends(get_db), _: User = Depends(current_user)):
    stmt = select(Product).where(_has_active_listing()).order_by(Product.id).limit(50)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.brand.ilike(like), Product.category.ilike(like), Product.model_no.ilike(like)))
    items = []
    for p in db.execute(stmt).scalars():
        a = cached_or_analyze(db, p)
        items.append(ProductSearchItem(**ProductOut.model_validate(p).model_dump(), lowest_price=a["current_price"],
                                       score=a["score"], label=a["label"]))
    return {"items": items}


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
    return ProductDetailOut(**ProductOut.model_validate(p).model_dump(), listings_count=cnt)


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

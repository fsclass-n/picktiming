import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# 상용 서비스 표준: 영문 대문자·소문자·숫자·특수문자를 모두 포함해 8자 이상
PASSWORD_RULE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).{8,72}$")
PASSWORD_MESSAGE = "비밀번호는 영문 대문자·소문자·숫자·특수문자를 모두 포함해 8자 이상이어야 합니다."


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- 인증
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)  # 길이·조합은 아래 규칙에서 한국어 안내와 함께 검사
    name: str = Field(min_length=1, max_length=50)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not PASSWORD_RULE.match(v):
            raise ValueError(PASSWORD_MESSAGE)
        return v


class DemoLoginIn(BaseModel):
    kind: Literal["user", "admin"] = "user"


class RoleIn(BaseModel):
    role: Literal["USER", "ADMIN"]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(ORM):
    id: int
    email: str
    name: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------------------------------------------------------- 상품
class ProductOut(ORM):
    id: int
    name: str
    brand: str
    model_no: str
    category: str
    image_url: str | None = None


class OfflinePriceOut(BaseModel):
    """한국소비자원 참가격: 오프라인 판매점(대형마트 등) 조사 가격 중 최저가(포장 수량 환산 후)"""
    price: int
    store_type: str | None = None
    survey_date: date


class ProductDetailOut(ProductOut):
    listings_count: int
    spec_summary: str | None = None
    offline_price: OfflinePriceOut | None = None


class ProductSearchItem(ProductOut):
    lowest_price: int | None = None
    score: int | None = None
    label: str = "HOLD"


class ProductRegisterIn(BaseModel):
    url: str = Field(min_length=10, max_length=500, pattern=r"^https?://")
    name: str | None = Field(default=None, max_length=100)


# ---------------------------------------------------------------- AI
class ChatIn(BaseModel):
    product_id: int
    question: str = Field(min_length=1, max_length=200)


# ---------------------------------------------------------------- 관심 상품
class WatchIn(BaseModel):
    product_id: int
    target_price: int | None = Field(default=None, ge=0)


class WatchPatch(BaseModel):
    target_price: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------- RPA
class PriceItem(BaseModel):
    listing_id: int
    price: int = Field(ge=0)
    shipping_fee: int = Field(default=0, ge=0)
    in_stock: bool = True
    # 가격 비교 사이트 JSON-LD의 부가 정보(선택). 값이 온 것만 판매처·상품에 덮어쓴다
    spec: str | None = Field(default=None, max_length=500)
    offer_count: int | None = Field(default=None, ge=0)
    high_price: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)


class PriceBulkIn(BaseModel):
    collected_at: datetime | None = None
    items: list[PriceItem] = Field(max_length=5000)


class PublicPriceItem(BaseModel):
    model_no: str
    good_id: str
    price: int = Field(ge=0)
    store_type: str | None = None
    survey_date: date


class PublicPriceIn(BaseModel):
    items: list[PublicPriceItem] = Field(max_length=5000)


class ModelUploadIn(BaseModel):
    version: str
    algorithm: str
    f1: float | None = None
    precision: float | None = None
    trained_rows: int = 0
    artifact_b64: str
    activate: bool = True


class JobLogIn(BaseModel):
    job_name: str = Field(max_length=50)
    status: str = Field(pattern=r"^(SUCCESS|PARTIAL|FAIL|RUNNING)$")
    collected: int = 0
    failed: int = 0
    message: str | None = Field(default=None, max_length=500)
    started_at: datetime
    ended_at: datetime | None = None


class EnsureListingsIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    base_url: str = Field(pattern=r"^https://", max_length=200)
    url_template: str = Field(pattern=r"^https://.*\{query\}", max_length=300)


# ---------------------------------------------------------------- 실제 수집 카탈로그(rpa/catalog.json → PUT /rpa/catalog)
class CatalogMallIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    base_url: str = Field(pattern=r"^https://[^/]+$", max_length=200)


class CatalogListingIn(BaseModel):
    mall: str = Field(min_length=1, max_length=50)
    url: str = Field(pattern=r"^https://", max_length=500)


class CatalogProductIn(BaseModel):
    # 사용자가 URL로 등록한 상품의 기본값 "-"과 겹치지 않게 실제 모델 번호만 허용
    model_no: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/+-]*$")
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="-", min_length=1, max_length=100)
    category: str = Field(default="기타", min_length=1, max_length=30)
    priority: int = Field(default=0, ge=0, le=1_000_000)
    image_url: str | None = Field(default=None, pattern=r"^https://", max_length=500)  # 제조사 공식 이미지만
    listings: list[CatalogListingIn] = Field(min_length=1, max_length=10)


class CatalogIn(BaseModel):
    malls: list[CatalogMallIn] = Field(min_length=1, max_length=20)
    products: list[CatalogProductIn] = Field(max_length=600)
    # 더 이상 수집하지 않을 쇼핑몰 도메인(예: 시연용 mall-a.example.com). 삭제하지 않고 is_active=False로 숨긴다
    retire_mall_hosts: list[str] = Field(default_factory=list, max_length=20)

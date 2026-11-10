"""ERD·테이블 정의서(설계 단계)의 12개 테이블"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import now_local
from .database import Base

BigId = Integer  # SQLite 자동 증가 호환을 위해 Integer 사용 (MySQL에서는 INT)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(10), default="USER")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str] = mapped_column(String(100), default="-")
    model_no: Mapped[str] = mapped_column(String(100), default="-", index=True)
    category: Mapped[str] = mapped_column(String(30), default="기타")
    # 수집 우선순위(높을수록 먼저, 인기 상품 찾기가 갱신). 수집 1회 상한(COLLECT_MAX_PRODUCTS)까지 높은 순으로 수집
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 제조사 공식 이미지 주소(직접 확인해 등록한 것만). 없으면 화면은 카테고리 아이콘 + 판매처 링크를 보여 준다
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    listings: Mapped[list["ProductListing"]] = relationship(back_populates="product")


class Mall(Base):
    __tablename__ = "malls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str] = mapped_column(String(200))
    robots_checked_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductListing(Base):
    __tablename__ = "product_listings"
    __table_args__ = (UniqueConstraint("product_id", "mall_id", name="uq_listing_product_mall"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    mall_id: Mapped[int] = mapped_column(ForeignKey("malls.id"))
    url: Mapped[str] = mapped_column(String(500))
    option_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    product: Mapped[Product] = relationship(back_populates="listings")
    mall: Mapped[Mall] = relationship()


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_listing_time", "listing_id", "collected_at"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("product_listings.id"))
    price: Mapped[int] = mapped_column(Integer)
    shipping_fee: Mapped[int] = mapped_column(Integer, default=0)
    total_price: Mapped[int] = mapped_column(Integer)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class PublicPrice(Base):
    __tablename__ = "public_prices"
    __table_args__ = (UniqueConstraint("product_id", "good_id", "survey_date", name="uq_public_price"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    good_id: Mapped[str] = mapped_column(String(50))
    price: Mapped[int] = mapped_column(Integer)
    store_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    survey_date: Mapped[date] = mapped_column(Date)


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_watch_user_product"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    target_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    product: Mapped[Product] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    type: Mapped[str] = mapped_column(String(20))  # TARGET_PRICE / TIMING_CHANGE
    message: Mapped[str] = mapped_column(String(300))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class TimingPrediction(Base):
    __tablename__ = "timing_predictions"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentile_90d: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_drop_7d: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(12))  # BUY_NOW / WAIT_A_BIT / WAIT / HOLD
    history_days: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)


class AiAdviceLog(Base):
    __tablename__ = "ai_advice_logs"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(10))  # ADVICE / CHAT
    cache_key: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="template")  # gemini / template
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    validation: Mapped[str] = mapped_column(String(20), default="OK")  # OK / RETRY / FALLBACK / ERROR / TEMPLATE
    advice_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(50))
    algorithm: Mapped[str] = mapped_column(String(50))
    f1: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    trained_rows: Mapped[int] = mapped_column(Integer, default=0)
    artifact: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(LONGBLOB, "mysql"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class RpaJobLog(Base):
    __tablename__ = "rpa_job_logs"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(10))  # SUCCESS / PARTIAL / FAIL / RUNNING
    collected: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

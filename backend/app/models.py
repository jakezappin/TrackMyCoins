from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(12, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoinType(Base):
    """A series of coins, e.g. Morgan Dollar. Shared across users."""

    __tablename__ = "coin_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    inventory_prefix: Mapped[str] = mapped_column(String(10), unique=True)
    # Mint marks valid for this series, e.g. ["P", "CC", "O", "S", "D"].
    mint_marks: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Synced from app/series.py at startup.
    plural: Mapped[str] = mapped_column(String(100), default="", server_default="")
    category: Mapped[str] = mapped_column(String(50), default="", server_default="")
    finishes: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["MS"], server_default='["MS"]')


class CatalogEntry(Base):
    """A Greysheet catalog item (one date/mint/designation/variety), cached locally for matching."""

    __tablename__ = "catalog_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_type_id: Mapped[int] = mapped_column(ForeignKey("coin_types.id"), index=True)
    gsid: Mapped[int] = mapped_column(Integer, unique=True)
    # Greysheet catalog section the entry came from (e.g. 10339 = $20 Liberty Type 1); used by type sets.
    node_id: Mapped[int | None] = mapped_column(Integer, index=True)
    pcgs_number: Mapped[str | None] = mapped_column(String(20), index=True)
    ngc_id: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    mint_mark: Mapped[str | None] = mapped_column(String(5))
    designation: Mapped[str | None] = mapped_column(String(20))  # e.g. PL, DMPL, RD, FB, RD CAM, DCAM; None if plain
    strike: Mapped[str] = mapped_column(String(5), default="MS")  # MS (business) | PR (proof)
    variety: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InventoryCounter(Base):
    """Next coin inventory number per (user, coin type). Never reused."""

    __tablename__ = "inventory_counters"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    coin_type_id: Mapped[int] = mapped_column(ForeignKey("coin_types.id"), primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer, default=1)


class CollectionCounter(Base):
    """Next collection number per (user, coin type, finish), e.g. /collections/kennedy-half-dollars-proof/3."""

    __tablename__ = "collection_counters"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    coin_type_id: Mapped[int] = mapped_column(ForeignKey("coin_types.id"), primary_key=True)
    finish: Mapped[str] = mapped_column(String(5), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        UniqueConstraint("user_id", "coin_type_id", "finish", "number", name="uq_collections_user_type_finish_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coin_type_id: Mapped[int] = mapped_column(ForeignKey("coin_types.id"))
    # MS (business strikes) | PR (proofs) | SPR (silver proofs); see app/series.py
    finish: Mapped[str] = mapped_column(String(5), default="MS", server_default="MS")
    # Per-user sequence within (coin type, finish), shown in URLs: /collections/morgan-dollars/1
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # When the owner last opened it (orders "Recent collections" on the dashboard).
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Read-only public link /shared/{share_token}; None = not shared. Regenerating it revokes old links.
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    share_show_values: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    user: Mapped["User"] = relationship()
    coin_type: Mapped[CoinType] = relationship()
    coins: Mapped[list["Coin"]] = relationship(back_populates="collection")


class Coin(Base):
    __tablename__ = "coins"
    __table_args__ = (UniqueConstraint("user_id", "inventory_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coin_type_id: Mapped[int] = mapped_column(ForeignKey("coin_types.id"), index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    inventory_number: Mapped[str] = mapped_column(String(20))

    # Identity
    year: Mapped[int] = mapped_column(Integer)
    mint_mark: Mapped[str] = mapped_column(String(5))  # "P" for no mint mark
    vam: Mapped[str | None] = mapped_column(String(50))
    # Catalog variety / issue, e.g. "8TF", "Alabama", "Type 2, Silver". Used to pick the right catalog entry.
    variety: Mapped[str | None] = mapped_column(String(150))
    # PCGS catalog number (e.g. 7226 = 1881-S MS). Identifies date/mint/designation for pricing.
    pcgs_number: Mapped[str | None] = mapped_column(String(20))

    # Grading
    grading_service: Mapped[str] = mapped_column(String(10))  # PCGS|NGC|ANACS|CACG|RAW
    cert_number: Mapped[str | None] = mapped_column(String(30), index=True)
    grade_prefix: Mapped[str | None] = mapped_column(String(5))  # MS, AU, XF, VF, PR ...
    grade: Mapped[int | None] = mapped_column(Integer)  # Sheldon 1-70
    grade_plus: Mapped[bool] = mapped_column(Boolean, default=False)
    grade_star: Mapped[bool] = mapped_column(Boolean, default=False)
    strike_designation: Mapped[str | None] = mapped_column(String(20))  # PL, DMPL, RD, FB, DCAM, "RD CAM" ...
    cac: Mapped[bool] = mapped_column(Boolean, default=False)
    cac_sticker: Mapped[str | None] = mapped_column(String(10))  # green | gold

    # Collector slabs
    slab_soapbox: Mapped[bool] = mapped_column(Boolean, default=False)
    slab_ngc_fatty: Mapped[bool] = mapped_column(Boolean, default=False)
    slab_rattler: Mapped[bool] = mapped_column(Boolean, default=False)
    slab_ogh: Mapped[bool] = mapped_column(Boolean, default=False)
    # GSA (General Services Administration) Carson City hoard holders; priced separately by Greysheet.
    gsa_hard_pack: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    gsa_soft_pack: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Original U.S. Mint packaging for 40% silver Ikes: Blue Pack (uncirculated), Brown Pack (proof).
    ike_blue_pack: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    ike_brown_pack: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # Toning
    toning_obverse: Mapped[bool] = mapped_column(Boolean, default=False)
    toning_reverse: Mapped[bool] = mapped_column(Boolean, default=False)
    toning_dual: Mapped[bool] = mapped_column(Boolean, default=False)
    toning_rainbow: Mapped[bool] = mapped_column(Boolean, default=False)

    # Estimated value used in totals: "cpg" = latest CPG + premiums below, or "custom" = custom_value.
    value_source: Mapped[str] = mapped_column(String(10), default="cpg", server_default="cpg")
    custom_value: Mapped[Decimal | None] = mapped_column(Money)
    # Extra value for attractive toning, added on top of CPG ("toner tax"). None = no premium.
    toner_premium: Mapped[Decimal | None] = mapped_column(Money)
    # Extra value for a desirable holder (Rattler, Fatty, OGH, GSA...) ("holder tax"). None = no premium.
    holder_premium: Mapped[Decimal | None] = mapped_column(Money)

    # Purchase
    price_paid: Mapped[Decimal | None] = mapped_column(Money)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchased_from: Mapped[str | None] = mapped_column(String(200))

    # Sale (both null = on hand)
    sale_price: Mapped[Decimal | None] = mapped_column(Money)
    sale_date: Mapped[date | None] = mapped_column(Date)
    sold_to: Mapped[str | None] = mapped_column(String(200))

    notes: Mapped[str | None] = mapped_column(Text)
    lookup_raw: Mapped[dict | None] = mapped_column(JSON)
    # Latest PCGS data for the coin's PCGS # and grade: price guide, population, recent auction sales.
    pcgs_market: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    coin_type: Mapped[CoinType] = relationship()
    collection: Mapped[Collection] = relationship(back_populates="coins")
    photos: Mapped[list["CoinPhoto"]] = relationship(
        back_populates="coin", cascade="all, delete-orphan", order_by="CoinPhoto.sort_order"
    )
    price_quotes: Mapped[list["PriceQuote"]] = relationship(
        back_populates="coin", cascade="all, delete-orphan", order_by="PriceQuote.fetched_at.desc()"
    )

    @property
    def is_sold(self) -> bool:
        return self.sale_date is not None or self.sale_price is not None


class CoinPhoto(Base):
    __tablename__ = "coin_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="upload")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    coin: Mapped[Coin] = relationship(back_populates="photos")


class PriceQuote(Base):
    __tablename__ = "price_quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # CPG | PCGS | MANUAL ...
    value: Mapped[Decimal | None] = mapped_column(Money)
    grade_used: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(String(255))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw: Mapped[dict | None] = mapped_column(JSON)

    coin: Mapped[Coin] = relationship(back_populates="price_quotes")

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
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
    # Details (problem) coins are valued at this % of straight-grade CPG unless the coin says otherwise.
    details_pct: Mapped[int] = mapped_column(Integer, default=70, server_default="70")
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


class CpgHistory(Base):
    """CPG for one grade of one issue over time, built from every price sheet the app fetches (shared by all
    users). A row covers first_seen..last_seen; a new row starts whenever the price changes."""

    __tablename__ = "cpg_history"
    __table_args__ = (Index("ix_cpg_history_lookup", "key", "label", "cac"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40))  # same as GradePriceSheet.key: "pcgs:7130" or "gsid:7434"
    grade: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(30))  # Greysheet's grade label, e.g. "MS64" or "MS64+"
    cac: Mapped[bool] = mapped_column(Boolean, default=False)
    value: Mapped[Decimal] = mapped_column(Money)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuctionSale(Base):
    """A PCGS-reported auction sale, kept for good: PCGS only returns about 3 years of sales, so this archive keeps
    what it drops. Each sale is stored once (`fingerprint`), however many coins or refreshes see it."""

    __tablename__ = "auction_sales"
    __table_args__ = (Index("ix_auction_sales_issue", "pcgs_number", "grade", "plus"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(40), unique=True)
    pcgs_number: Mapped[str] = mapped_column(String(20))
    grade: Mapped[int] = mapped_column(Integer)
    plus: Mapped[bool] = mapped_column(Boolean, default=False)
    sale_month: Mapped[str] = mapped_column(String(7))  # "2024-03" (PCGS gives month and year)
    price: Mapped[Decimal] = mapped_column(Money)
    service: Mapped[str | None] = mapped_column(String(10))  # who graded the coin sold: PCGS, NGC...
    cac: Mapped[bool] = mapped_column(Boolean, default=False)
    auctioneer: Mapped[str | None] = mapped_column(String(100))
    lot: Mapped[str | None] = mapped_column(String(40))
    cert_number: Mapped[str | None] = mapped_column(String(30))
    url: Mapped[str | None] = mapped_column(String(500))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuctionFetch(Base):
    """When the full sales list (~3 years) for an issue and grade was last fetched from PCGS."""

    __tablename__ = "auction_fetches"
    __table_args__ = (UniqueConstraint("pcgs_number", "grade", "plus"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pcgs_number: Mapped[str] = mapped_column(String(20))
    grade: Mapped[int] = mapped_column(Integer)
    plus: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sales_seen: Mapped[int] = mapped_column(Integer, default=0)


class PcgsGuideHistory(Base):
    """PCGS Price Guide value for an issue and grade over time; a new row only when it changes."""

    __tablename__ = "pcgs_guide_history"
    __table_args__ = (Index("ix_pcgs_guide_issue", "pcgs_number", "grade", "plus"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pcgs_number: Mapped[str] = mapped_column(String(20))
    grade: Mapped[int] = mapped_column(Integer)
    plus: Mapped[bool] = mapped_column(Boolean, default=False)
    value: Mapped[Decimal] = mapped_column(Money)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GradePriceSheet(Base):
    """CPG prices for every grade of one issue (one Greysheet call returns them all). Shared by every coin of
    that issue, so the price-by-grade table costs no extra API calls."""

    __tablename__ = "grade_price_sheets"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # "pcgs:7124" or "gsid:7434"
    gsid: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(255))
    rows: Mapped[list] = mapped_column(JSON)  # [{"grade": 63, "label": "MS63", "cac": false, "cpg": "130.00"}, ...]
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CoinAttachment(Base):
    """A receipt, invoice or other document kept with a coin (PDF or image). Private: never on shared pages."""

    __tablename__ = "coin_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(80))  # stored name
    original_name: Mapped[str] = mapped_column(String(200))  # as uploaded, for display and download
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WantItem(Base):
    """A coin the user is looking for: date, mint, variety, target grade and the most they'd pay."""

    __tablename__ = "want_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id", ondelete="SET NULL"))
    coin_type_id: Mapped[int] = mapped_column(ForeignKey("coin_types.id"))
    finish: Mapped[str] = mapped_column(String(5), default="MS", server_default="MS")
    year: Mapped[int] = mapped_column(Integer)
    mint_mark: Mapped[str] = mapped_column(String(5))
    variety: Mapped[str | None] = mapped_column(String(150))
    grade_prefix: Mapped[str | None] = mapped_column(String(5))
    grade: Mapped[int | None] = mapped_column(Integer)
    max_price: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    coin_type: Mapped[CoinType] = relationship()
    collection: Mapped["Collection | None"] = relationship()


class ApiUsage(Base):
    """Calls made to paid / rate-limited services, per day: per user, and site-wide (user_id 0)."""

    __tablename__ = "api_usage"
    __table_args__ = (UniqueConstraint("day", "user_id", "service"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    user_id: Mapped[int] = mapped_column(Integer)  # 0 = whole site
    service: Mapped[str] = mapped_column(String(20))  # claude | greysheet | pcgs
    count: Mapped[int] = mapped_column(Integer, default=0)


class PriceRefreshRun(Base):
    """One use of "Refresh prices" (to cap how often a user can refresh in bulk, which spends API calls)."""

    __tablename__ = "price_refresh_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Set when the run ends. A run cut short (e.g. Fly stopped the machine) never gets one and, after a grace
    # period, stops counting against the weekly limit.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(String(200))


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
    # Where the coin is: "inventory" (with the owner) or "grading" (out at a grader, in a GradingSubmission).
    location: Mapped[str] = mapped_column(String(12), default="inventory", server_default="inventory")
    # Details grade ("AU Details – Cleaned"): genuine but with a problem, so not priced like a straight grade.
    # The grade number is optional (PCGS and NGC usually give only AU, XF...).
    details: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    details_problem: Mapped[str | None] = mapped_column(String(40))  # cleaned, environmental-damage...
    details_pct: Mapped[int | None] = mapped_column(Integer)  # this coin's % of straight CPG (None: the owner's default)

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
    # Still in its Original Government Packaging (modern commemoratives, Blue/Brown Pack Ikes).
    ogp: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Mint & proof sets: coins moved to (or kept alongside) a Capital Plastics holder.
    capital_holder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

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
    # Estimated value at purchase: the owner's own figure, else worked out (see services/purchase_value.py).
    purchase_value_custom: Mapped[Decimal | None] = mapped_column(Money)
    # Average of PCGS auction sales near the purchase date, saved because PCGS only keeps ~3 years of sales.
    # `purchase_auction_key` is what it was worked out for (PCGS #, grade, purchase date); a change redoes it.
    purchase_auction_value: Mapped[Decimal | None] = mapped_column(Money)
    purchase_auction_count: Mapped[int | None] = mapped_column(Integer)
    purchase_auction_span: Mapped[str | None] = mapped_column(String(20))  # "2024-01..2024-05"
    purchase_auction_key: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    coin_type: Mapped[CoinType] = relationship()
    collection: Mapped[Collection] = relationship(back_populates="coins")
    user: Mapped[User] = relationship()
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
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)  # when this price began
    # Last time the same price was seen again (a check that found no change doesn't add a row).
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSON)

    coin: Mapped[Coin] = relationship(back_populates="price_quotes")


# ---- Bullion: kept apart from the numismatic collections (no grades, catalog or price guides) ----------------

class BullionCollection(Base):
    """A user's bullion stack for one metal (silver, gold, platinum or palladium)."""

    __tablename__ = "bullion_collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    metal: Mapped[str] = mapped_column(String(12))  # silver | gold | platinum | palladium
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["BullionItem"]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class BullionItem(Base):
    """A bar, round, coin, roll or tube. Pure metal = weight x purity x quantity, or face value for junk silver."""

    __tablename__ = "bullion_items"
    __table_args__ = (UniqueConstraint("user_id", "inventory_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("bullion_collections.id", ondelete="CASCADE"), index=True)
    inventory_number: Mapped[str] = mapped_column(String(20))  # "AG-00001"
    description: Mapped[str] = mapped_column(String(200))  # "Buffalo Round", "Silvertown Bar"
    packaging: Mapped[str] = mapped_column(String(20), default="single")  # single | roll | tube | box
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # per piece
    weight_unit: Mapped[str] = mapped_column(String(4), default="ozt")  # ozt | g | kg
    purity: Mapped[Decimal] = mapped_column(Numeric(6, 5))  # 0.999
    face_value: Mapped[Decimal | None] = mapped_column(Money)  # junk silver: "$10 face" instead of weight
    price_paid: Mapped[Decimal | None] = mapped_column(Money)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchased_from: Mapped[str | None] = mapped_column(String(200))
    sale_price: Mapped[Decimal | None] = mapped_column(Money)
    sale_date: Mapped[date | None] = mapped_column(Date)
    sold_to: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    collection: Mapped[BullionCollection] = relationship(back_populates="items")
    photos: Mapped[list["BullionPhoto"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="BullionPhoto.sort_order"
    )


class BullionPhoto(Base):
    __tablename__ = "bullion_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("bullion_items.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(50))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[BullionItem] = relationship(back_populates="photos")


class BullionAttachment(Base):
    """A receipt, invoice or other document kept with a bullion item (PDF or photo). Private."""

    __tablename__ = "bullion_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("bullion_items.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(80))
    original_name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BullionCounter(Base):
    """Next bullion inventory number per (user, metal): AG-00001, AU-00001... Never reused."""

    __tablename__ = "bullion_counters"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    metal: Mapped[str] = mapped_column(String(12), primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer, default=1)


class SpotPrice(Base):
    """Daily spot price (USD per troy ounce) per metal: the history behind bullion values over time."""

    __tablename__ = "spot_prices"
    __table_args__ = (UniqueConstraint("metal", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metal: Mapped[str] = mapped_column(String(12))
    day: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    source: Mapped[str] = mapped_column(String(20), default="live")  # live | history


# ---- Grading Tracker: coins sent to NGC, PCGS, CAC... ------------------------------------------------------

class GradingSubmission(Base):
    """One package of coins sent to a grading company: its service tier (fees and turnaround as they were when it
    was sent), dates, tracking, costs and the coins in it."""

    __tablename__ = "grading_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)  # 1, 2, 3... per user
    name: Mapped[str | None] = mapped_column(String(100))  # the owner's label, e.g. "Morgans for NGC"
    company: Mapped[str] = mapped_column(String(10))  # NGC | PCGS | CAC | CACG | ANACS | ICG
    kind: Mapped[str] = mapped_column(String(12), default="grading")  # grading | crossover | regrade | reholder | sticker
    # The service tier, copied from the tier list when chosen (the owner can change any of it).
    tier_key: Mapped[str | None] = mapped_column(String(60))
    tier_name: Mapped[str | None] = mapped_column(String(100))
    tier_fee: Mapped[Decimal | None] = mapped_column(Money)  # per coin
    tier_max_value: Mapped[Decimal | None] = mapped_column(Money)  # per coin
    turnaround_days: Mapped[int | None] = mapped_column(Integer)
    business_days: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    addons: Mapped[list] = mapped_column(JSON, default=list)  # [{"key", "name", "fee", "per": "coin"|"order"}]
    order_number: Mapped[str | None] = mapped_column(String(60))
    tracking_out: Mapped[str | None] = mapped_column(String(60))
    tracking_back: Mapped[str | None] = mapped_column(String(60))
    date_sent: Mapped[date | None] = mapped_column(Date)
    date_received: Mapped[date | None] = mapped_column(Date)  # by the grader: the turnaround clock starts
    date_shipped_back: Mapped[date | None] = mapped_column(Date)
    date_returned: Mapped[date | None] = mapped_column(Date)  # back with the owner
    grading_paid: Mapped[Decimal | None] = mapped_column(Money)
    shipping_paid: Mapped[Decimal | None] = mapped_column(Money)  # shipping, insurance, registered mail
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "number"),)
    coins: Mapped[list["GradingSubmissionCoin"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="GradingSubmissionCoin.id")


class GradingSubmissionCoin(Base):
    """A coin in a submission: what was expected, and (once back) what it came back as. Kept after the coin returns:
    the coin's grading history."""

    __tablename__ = "grading_submission_coins"
    __table_args__ = (UniqueConstraint("submission_id", "coin_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("grading_submissions.id", ondelete="CASCADE"), index=True)
    coin_id: Mapped[int] = mapped_column(ForeignKey("coins.id", ondelete="CASCADE"), index=True)
    expected_grade: Mapped[str | None] = mapped_column(String(20))  # "MS65", "PR69 DCAM", "Green sticker"
    declared_value: Mapped[Decimal | None] = mapped_column(Money)
    # Before: the coin as sent ("Raw", "NGC MS64 #1234567-001").
    before: Mapped[dict | None] = mapped_column(JSON)
    # Result: pending | graded | details | no_grade | not_crossed | sticker_green | sticker_gold | no_sticker | returned
    outcome: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    after: Mapped[dict | None] = mapped_column(JSON)  # the grade it came back with
    returned_on: Mapped[date | None] = mapped_column(Date)

    submission: Mapped[GradingSubmission] = relationship(back_populates="coins")
    coin: Mapped["Coin"] = relationship()


class GradingAttachment(Base):
    """An invoice, shipping receipt, insurance or registered-mail slip kept with a submission (PDF or photo)."""

    __tablename__ = "grading_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("grading_submissions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="other")  # invoice | shipping | insurance | registered | other
    file_name: Mapped[str] = mapped_column(String(80))
    original_name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

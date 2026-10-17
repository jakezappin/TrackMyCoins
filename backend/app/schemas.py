from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .designations import canonical

GradingService = Literal["PCGS", "NGC", "ANACS", "CACG", "RAW"]
CacSticker = Literal["green", "gold"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth -------------------------------------------------------------------


class SignupIn(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=200)
    invite_code: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    current_password: str | None = None  # required only when changing email


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class UserOut(ORM):
    id: int
    email: str
    first_name: str
    last_name: str


# ---- Coin types / collections ------------------------------------------------


class FinishOut(BaseModel):
    code: str  # MS | PR | SPR
    label: str  # "MS" | "Proof" | "Silver Proof"
    collection_type_slug: str  # e.g. "kennedy-half-dollars-proof"
    collection_type_label: str  # e.g. "Kennedy Half Dollars – Proof"


class CoinTypeOut(ORM):
    id: int
    name: str
    plural: str
    slug: str
    category: str
    inventory_prefix: str
    mint_marks: list[str]
    finishes: list[FinishOut]
    metal: str = "silver"  # "gold" | "silver", for placeholder artwork


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    coin_type_id: int
    finish: Literal["MS", "PR", "SPR"] = "MS"


class CollectionRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CollectionSummary(BaseModel):
    coin_count: int
    total_price_paid: Decimal
    total_cpg_value: Decimal
    est_wholesale_value: Decimal
    unpriced_count: int


class CollectionOut(ORM):
    id: int
    number: int
    name: str
    coin_type_id: int
    coin_type_slug: str
    finish: str
    collection_type_slug: str  # URL segment, e.g. "kennedy-half-dollars-proof"
    collection_type_label: str  # e.g. "Kennedy Half Dollars – Proof"
    created_at: datetime
    last_viewed_at: datetime | None = None


class CollectionWithSummary(CollectionOut):
    summary: CollectionSummary


# ---- Coins --------------------------------------------------------------------


class CoinFields(BaseModel):
    year: int = Field(ge=1700, le=2200)
    mint_mark: str = Field(min_length=1, max_length=5)
    vam: str | None = Field(default=None, max_length=50)
    variety: str | None = Field(default=None, max_length=150)
    pcgs_number: str | None = Field(default=None, max_length=20)

    grading_service: GradingService
    cert_number: str | None = Field(default=None, max_length=30)
    grade_prefix: str | None = Field(default=None, max_length=5)
    grade: int | None = Field(default=None, ge=1, le=70)
    grade_plus: bool = False
    grade_star: bool = False
    strike_designation: str | None = Field(default=None, max_length=20)
    cac: bool = False
    cac_sticker: CacSticker | None = None

    slab_soapbox: bool = False
    slab_ngc_fatty: bool = False
    slab_rattler: bool = False
    slab_ogh: bool = False
    gsa_hard_pack: bool = False
    gsa_soft_pack: bool = False
    ike_blue_pack: bool = False
    ike_brown_pack: bool = False

    toning_obverse: bool = False
    toning_reverse: bool = False
    toning_dual: bool = False
    toning_rainbow: bool = False

    price_paid: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    purchase_date: date | None = None
    purchased_from: str | None = Field(default=None, max_length=200)

    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sale_date: date | None = None
    sold_to: str | None = Field(default=None, max_length=200)

    notes: str | None = None

    @field_validator("strike_designation", mode="before")
    @classmethod
    def _designation(cls, v):
        return canonical(v) if isinstance(v, str) else v

    @field_validator("mint_mark", "grade_prefix", mode="before")
    @classmethod
    def _upper(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v

    @field_validator("cert_number", "vam", "variety", "pcgs_number", "purchased_from", "sold_to", "notes", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class CoinIn(CoinFields):
    collection_id: int
    lookup_raw: dict | None = None


class CoinUpdate(CoinFields):
    collection_id: int


class PhotoOut(ORM):
    id: int
    sort_order: int
    source: str
    url: str


class PriceQuoteOut(ORM):
    id: int
    source: str
    value: Decimal | None
    grade_used: str | None
    description: str | None
    fetched_at: datetime


class CoinOut(CoinFields, ORM):
    id: int
    coin_type_id: int
    collection_id: int
    inventory_number: str
    is_sold: bool
    created_at: datetime
    updated_at: datetime
    latest_cpg: PriceQuoteOut | None = None
    latest_greysheet: PriceQuoteOut | None = None
    photo_count: int = 0
    thumbnail_url: str | None = None
    coin_type_slug: str = ""
    collection_type_slug: str = ""
    collection_number: int = 0
    finish: str = "MS"


class AuctionSale(BaseModel):
    date: str  # "YYYY-MM"
    price: Decimal
    auctioneer: str | None = None
    sale_name: str | None = None
    lot: str | None = None
    url: str | None = None
    service: str | None = None  # PCGS | NGC
    cert_number: str | None = None
    cac: bool = False


class PcgsMarket(BaseModel):
    fetched_at: datetime
    pcgs_number: str
    grade: str  # e.g. "MS62", "MS64+"
    price_guide: Decimal | None = None
    population: int | None = None
    pop_higher: int | None = None
    coinfacts_url: str | None = None
    auctions: list[AuctionSale] = []


class CoinDetail(CoinOut):
    pcgs_market: PcgsMarket | None = None
    photos: list[PhotoOut]
    price_quotes: list[PriceQuoteOut]
    collection_name: str


class ManualQuoteIn(BaseModel):
    source: str = Field(default="CPG", max_length=20)
    value: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=255)


class PhotoImportIn(BaseModel):
    urls: list[str] = Field(max_length=10)


class PhotoReorderIn(BaseModel):
    photo_ids: list[int]


# ---- Lookups --------------------------------------------------------------------


class LookupResult(BaseModel):
    """Normalized result of a cert lookup. Every field is optional; the user reviews before saving."""

    grading_service: GradingService
    cert_number: str
    year: int | None = None
    mint_mark: str | None = None
    grade_prefix: str | None = None
    grade: int | None = None
    grade_plus: bool = False
    grade_star: bool = False
    strike_designation: str | None = None
    vam: str | None = None
    pcgs_number: str | None = None
    cac: bool | None = None
    cac_sticker: CacSticker | None = None
    description: str | None = None
    image_urls: list[str] = []
    price_guide_value: Decimal | None = None
    verify_url: str | None = None
    warnings: list[str] = []
    raw: dict | None = None

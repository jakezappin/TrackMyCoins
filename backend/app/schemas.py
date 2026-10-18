import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .designations import canonical, unknown
from .urls import absolute_url

GradingService = Literal["PCGS", "NGC", "ANACS", "CACG", "ICG", "OTHER", "RAW"]
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
    details_pct: int = 70
    # Price code for labels (see services/price_code.py).
    price_code_phrase: str | None = None
    price_code_start: int | None = None
    price_code_length: int = 6
    asking_price_on: bool = False


class Preferences(BaseModel):
    # Details (problem) coins are valued at this % of straight-grade CPG.
    details_pct: int | None = Field(default=None, ge=1, le=100)
    # An Asking price field on each coin and bullion item.
    asking_price_on: bool | None = None


class PriceCodeIn(BaseModel):
    """None for the phrase: no price code."""

    phrase: str | None = Field(default=None, max_length=60)
    start: Literal[0, 1] | None = None
    length: int = Field(6, ge=3, le=10)


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
    is_type_set: bool = False
    is_set: bool = False  # a mint or proof set series: ungraded, priced in OGP
    member_ids: list[int] = []  # type sets: the series their coins can come from


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    coin_type_id: int
    finish: Literal["MS", "PR", "SPR"] = "MS"


class CollectionRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CollectionSummary(BaseModel):
    coin_count: int
    total_price_paid: Decimal
    total_estimated_value: Decimal  # what totals use: CPG (+ toner premiums) or the owner's own values
    total_cpg_value: Decimal  # CPG part only (coins valued from CPG)
    est_wholesale_value: Decimal  # estimated value - wholesale discount
    unpriced_count: int  # coins with no estimated value yet
    toner_count: int = 0  # coins whose value includes a toner premium
    toner_premium_total: Decimal = Decimal(0)
    holder_count: int = 0  # coins whose value includes a holder premium
    holder_premium_total: Decimal = Decimal(0)
    custom_count: int = 0  # coins valued at the owner's own figure


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
    share_token: str | None = None
    share_show_values: bool = False


class CollectionWithSummary(CollectionOut):
    summary: CollectionSummary


# ---- Coins --------------------------------------------------------------------


# Grades a coin can carry: business strikes, proofs (PR), specimens (SP) and circulated grades.
GRADE_PREFIXES = {"MS", "PR", "SP", "AU", "XF", "VF", "F", "VG", "G", "AG", "FR", "PO"}


class CoinFields(BaseModel):
    year: int = Field(ge=1700)
    mint_mark: str = Field(min_length=1, max_length=5)
    vam: str | None = Field(default=None, max_length=50)
    variety: str | None = Field(default=None, max_length=150)
    pcgs_number: str | None = Field(default=None, max_length=20)

    grading_service: GradingService
    # OTHER: the grading company's name (PCI, TruGrade, SEGS...).
    other_service: str | None = Field(default=None, max_length=60)
    cert_number: str | None = Field(default=None, max_length=30)
    grade_prefix: str | None = Field(default=None, max_length=5)
    grade: int | None = Field(default=None, ge=1, le=70)
    grade_plus: bool = False
    grade_star: bool = False
    strike_designation: str | None = Field(default=None, max_length=20)
    cac: bool = False
    cac_sticker: CacSticker | None = None
    # Details grade: genuine, but with a problem (cleaned, damaged...). Valued at details_pct% of straight CPG.
    details: bool = False
    details_problem: str | None = Field(default=None, max_length=40)
    details_pct: int | None = Field(default=None, ge=1, le=100)
    # Mint error: described by the owner, valued by the owner (no catalog, CPG or auction data).
    is_error: bool = False
    error_description: str | None = Field(default=None, max_length=200)
    # In the owner's hands, or out at a grading company (in a Grading Tracker submission).
    location: Literal["inventory", "grading"] = "inventory"
    # What the owner would sell it for (printed on its label).
    asking_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    # Where it's kept (a Storage spot) and where in it, e.g. "Page 3, hole 14".
    storage_id: int | None = None
    storage_position: str | None = Field(default=None, max_length=60)

    slab_soapbox: bool = False
    slab_ngc_fatty: bool = False
    slab_rattler: bool = False
    slab_ogh: bool = False
    gsa_hard_pack: bool = False
    gsa_soft_pack: bool = False
    ike_blue_pack: bool = False
    ike_brown_pack: bool = False
    ogp: bool = False  # Original Government Packaging
    capital_holder: bool = False  # mint & proof sets

    toning_obverse: bool = False
    toning_reverse: bool = False
    toning_dual: bool = False
    toning_rainbow: bool = False
    toning_rim: bool = False

    price_paid: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    purchase_value_custom: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    purchase_date: date | None = None
    purchased_from: str | None = Field(default=None, max_length=200)
    # Picked from the user's Dealers: links the coin to the dealer (the text above then shows the dealer's name).
    purchased_from_dealer_id: int | None = None
    sold_to_dealer_id: int | None = None

    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sale_date: date | None = None
    sold_to: str | None = Field(default=None, max_length=200)

    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("year")
    @classmethod
    def _year(cls, v: int):
        if v > date.today().year + 1:  # next year's issues (e.g. bullion) go on sale late in the year
            raise ValueError(f"{v} is in the future. Check the year.")
        return v

    @field_validator("grade_prefix")
    @classmethod
    def _grade_prefix(cls, v):
        if v is None:
            return v
        v = {"PF": "PR", "PROOF": "PR", "EF": "XF"}.get(v, v)
        if v not in GRADE_PREFIXES:
            raise ValueError(f"Unknown grade “{v}”. Use one of {', '.join(sorted(GRADE_PREFIXES))}.")
        return v

    @field_validator("cert_number")
    @classmethod
    def _cert(cls, v):
        if v and not re.fullmatch(r"[0-9A-Za-z-]+", v):
            raise ValueError("Cert numbers are letters, digits and dashes only (e.g. 12345678 or 1234567-001).")
        return v

    @field_validator("pcgs_number")
    @classmethod
    def _pcgs_number(cls, v):
        if v and not re.fullmatch(r"\d{1,8}", v):
            raise ValueError("A PCGS coin number is digits only (e.g. 7130).")
        return v

    @model_validator(mode="after")
    def _error(self):
        if not self.is_error:
            self.error_description = None
        elif not self.error_description:
            raise ValueError("Describe the error, e.g. Off-center 20%, Double struck, Broadstrike.")
        return self

    @model_validator(mode="after")
    def _details(self):
        from .services.details import PROBLEMS

        if not self.details:
            self.details_problem = None
            self.details_pct = None
            return self
        if self.cac:
            raise ValueError("CAC doesn't sticker Details coins. Untick CAC or Details.")
        if self.details_problem and self.details_problem not in PROBLEMS:
            raise ValueError(f"Unknown problem “{self.details_problem}”.")
        if self.grading_service != "RAW" and not self.grade_prefix:
            raise ValueError("A Details coin still needs its grade, e.g. AU (AU Details).")
        # Details grades carry no plus or star.
        self.grade_plus = False
        self.grade_star = False
        return self

    @model_validator(mode="after")
    def _other_service(self):
        if self.grading_service == "OTHER":
            if not self.other_service:
                raise ValueError("Enter the name of the grading company.")
        else:
            self.other_service = None
        return self

    @model_validator(mode="after")
    def _sale_after_purchase(self):
        if self.purchase_date and self.sale_date and self.sale_date < self.purchase_date:
            raise ValueError("The sale date is before the purchase date.")
        return self

    @field_validator("purchase_date", "sale_date")
    @classmethod
    def _sensible_date(cls, v, info):
        """Catch typos like year 0017 or 2107 (they wreck the value-over-time chart)."""
        if v is None:
            return v
        label = "Purchase date" if info.field_name == "purchase_date" else "Sale date"
        if v.year < 1900:
            raise ValueError(f"{label} {v.isoformat()} looks mistyped. Use the full year, e.g. {v.year % 100 + 2000}.")
        if v > date.today() + timedelta(days=1):
            raise ValueError(f"{label} {v.isoformat()} is in the future.")
        return v

    @field_validator("strike_designation", mode="before")
    @classmethod
    def _designation(cls, v):
        if isinstance(v, str):
            bad = unknown(v)
            if bad:
                raise ValueError(f"Unknown designation “{' '.join(bad)}”. Use PL, DMPL, RD, RB, BN, CAM, DCAM, FB, FBL, "
                                 "FS, FH or FT (Cameo, Red, Full Torch... are understood too).")
            return canonical(v)
        return v

    @field_validator("mint_mark", "grade_prefix", mode="before")
    @classmethod
    def _upper(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v

    @field_validator("cert_number", "vam", "variety", "pcgs_number", "purchased_from", "sold_to", "notes",
                     "storage_position", "error_description", "other_service", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


def small_json(v: dict | None, limit: int = 100_000) -> dict | None:
    """A lookup result sent back by the browser: kept, but never megabytes of it."""
    import json

    if v is not None and len(json.dumps(v, default=str)) > limit:
        raise ValueError("The lookup data sent with this coin is too large.")
    return v


class GradingChoice(BaseModel):
    """Sent with a coin marked At Grading: which submission it's in (or a new one for this company)."""

    submission_id: int | None = None
    new_company: Literal["NGC", "PCGS", "CACG", "CAC", "ANACS", "ICG"] | None = None
    expected_grade: str | None = Field(default=None, max_length=20)
    declared_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class NewCollectionPick(BaseModel):
    """From the coin search: no collection of this series and finish yet, so one is created with the coin."""

    coin_type_id: int
    finish: Literal["MS", "PR", "SPR"] = "MS"


class CoinIn(CoinFields):
    collection_id: int  # 0 with `new_collection`: create the collection
    grading: GradingChoice | None = None
    new_collection: NewCollectionPick | None = None
    # Error coins: the owner's estimated value, entered on the form.
    error_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    # Only for type set collections: which member series the coin belongs to.
    coin_type_id: int | None = None
    lookup_raw: dict | None = None

    @field_validator("lookup_raw")
    @classmethod
    def _small_lookup(cls, v):
        return small_json(v)


class CoinUpdate(CoinFields):
    collection_id: int
    grading: GradingChoice | None = None
    error_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    coin_type_id: int | None = None


class PhotoOut(ORM):
    id: int
    sort_order: int
    source: str
    url: str
    thumb_url: str


class PriceQuoteOut(ORM):
    id: int
    source: str
    value: Decimal | None
    grade_used: str | None
    description: str | None
    fetched_at: datetime
    confirmed_at: datetime | None = None


class CoinOut(CoinFields, ORM):
    """A saved coin, shown as it is. CoinFields' rules are for what's typed in: re-checking saved coins against them
    (a year-0017 date from an old import, a designation added to the rules later) would break the whole page."""

    @field_validator("year")
    @classmethod
    def _year(cls, v):
        return v

    @field_validator("grade_prefix")
    @classmethod
    def _grade_prefix(cls, v):
        return v

    @field_validator("cert_number")
    @classmethod
    def _cert(cls, v):
        return v

    @field_validator("pcgs_number")
    @classmethod
    def _pcgs_number(cls, v):
        return v

    @field_validator("purchase_date", "sale_date")
    @classmethod
    def _sensible_date(cls, v, info):
        return v

    @field_validator("strike_designation", mode="before")
    @classmethod
    def _designation(cls, v):
        return v

    @model_validator(mode="after")
    def _error(self):
        return self

    @model_validator(mode="after")
    def _details(self):
        return self

    @model_validator(mode="after")
    def _sale_after_purchase(self):
        return self

    @model_validator(mode="after")
    def _other_service(self):
        return self

    id: int
    coin_type_id: int
    collection_id: int
    inventory_number: str
    is_sold: bool
    created_at: datetime
    updated_at: datetime
    latest_cpg: PriceQuoteOut | None = None
    value_source: str = "cpg"
    custom_value: Decimal | None = None
    toner_premium: Decimal | None = None
    holder_premium: Decimal | None = None
    value_estimate: Decimal | None = None  # what totals use for this coin
    details_basis: str | None = None  # how a Details coin's value was worked out
    details_value: Decimal | None = None  # a Details coin's share of CPG (before premiums)
    # The submission it's in while at grading: {"id", "number", "company", "company_label", "status"}.
    grading: dict | None = None
    storage_name: str | None = None
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

    @field_validator("url")
    @classmethod
    def _absolute(cls, v):
        return absolute_url(v)


class CoinSpecs(BaseModel):
    mintage: int | None = None
    mint_location: str | None = None
    metal: str | None = None
    weight_g: float | None = None
    diameter_mm: float | None = None
    edge: str | None = None
    designer: str | None = None
    series: str | None = None


class CoinFacts(CoinSpecs):
    """Mintage, specs and PCGS population, from data already fetched (PCGS market data or a PCGS cert lookup)."""

    population: int | None = None
    pop_higher: int | None = None
    pop_grade: str | None = None  # the grade the population is for, e.g. "MS65"
    as_of: datetime | None = None
    source: str  # "pcgs_market" | "cert_lookup"
    pcgs_number: str | None = None
    melt: dict | None = None  # {"value", "metals": [{"metal", "oz", "spot"}], "as_of"}; silver/gold coins only


class PcgsMarket(BaseModel):
    fetched_at: datetime
    facts: CoinSpecs | None = None
    pcgs_number: str
    grade: str  # e.g. "MS62", "MS64+"
    price_guide: Decimal | None = None
    population: int | None = None
    pop_higher: int | None = None
    coinfacts_url: str | None = None
    auctions: list[AuctionSale] = []

    @field_validator("coinfacts_url")
    @classmethod
    def _absolute(cls, v):  # also fixes links saved before this was handled
        return absolute_url(v)


class PurchaseValue(BaseModel):
    """Estimated value at purchase and where it came from (custom | cpg | cpg_history | auctions | paid)."""

    value: Decimal | None = None
    source: str | None = None
    detail: str = ""
    pending: bool = False  # auction sales not looked up yet


class CoinDetail(CoinOut):
    purchase_value: PurchaseValue | None = None
    set_melt: dict | None = None  # mint & proof sets: {'oz', 'spot', 'value', 'as_of'}
    pcgs_market: PcgsMarket | None = None
    facts: CoinFacts | None = None
    photos: list[PhotoOut]
    price_quotes: list[PriceQuoteOut]
    collection_name: str
    grading_history: list[dict] = []  # trips to the graders, newest first


class ValuationIn(BaseModel):
    source: Literal["cpg", "custom"] = "cpg"
    custom_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    toner_premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)  # cpg only
    holder_premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)  # cpg only


class ImportValuation(BaseModel):
    """Value fields carried by an imported spreadsheet row."""

    value_source: Literal["cpg", "custom"] = "cpg"
    custom_value: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    toner_premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    holder_premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ManualQuoteIn(BaseModel):
    source: Literal["CPG", "PCGS", "GREYSHEET", "cpg", "pcgs", "greysheet"] = "CPG"
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
    variety: str | None = None  # overdate / over-mintmark from the name, e.g. "1880/79", "O/S"
    pcgs_number: str | None = None
    cac: bool | None = None
    cac_sticker: CacSticker | None = None
    details: bool = False
    details_problem: str | None = None
    description: str | None = None
    image_urls: list[str] = []
    price_guide_value: Decimal | None = None
    verify_url: str | None = None
    warnings: list[str] = []
    raw: dict | None = None


# ---- Shared (public, read-only) collections --------------------------------------------------


class ShareIn(BaseModel):
    show_values: bool = False


class SharedCoin(BaseModel):
    """What a visitor to a shared link sees: no cost, seller, notes or sale details."""

    id: int
    year: int
    mint_mark: str
    vam: str | None
    variety: str | None
    grading_service: str
    other_service: str | None = None
    cert_number: str | None
    grade_prefix: str | None
    grade: int | None
    grade_plus: bool
    grade_star: bool
    strike_designation: str | None
    cac: bool
    cac_sticker: str | None
    details: bool = False
    details_problem: str | None = None
    slab_soapbox: bool
    slab_ngc_fatty: bool
    slab_rattler: bool
    slab_ogh: bool
    gsa_hard_pack: bool
    gsa_soft_pack: bool
    ike_blue_pack: bool
    ike_brown_pack: bool
    ogp: bool = False
    capital_holder: bool = False
    toning_obverse: bool
    toning_reverse: bool
    toning_dual: bool
    toning_rainbow: bool
    toning_rim: bool = False
    is_error: bool = False
    error_description: str | None = None
    value_estimate: Decimal | None = None  # only when the owner chose to show values
    photo_urls: list[str]
    thumb_url: str | None = None


class SharedCollection(BaseModel):
    name: str
    owner: str  # "Jane D."
    collection_type_label: str
    coin_type_name: str
    metal: str
    show_values: bool
    coin_count: int
    total_estimated_value: Decimal | None = None
    coins: list[SharedCoin]

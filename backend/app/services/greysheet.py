"""Greysheet / CDN Public API v2: catalog browsing and CPG retail pricing.

Overview: https://publicapiv2.greysheet.com/
Spec:     https://cpgpublicapiv2beta.greysheet.com/openapi
Auth: x-api-key + x-api-token headers. The Basic tier returns CpgVal.
"""

import re
from decimal import Decimal, InvalidOperation

import httpx

from ..config import get_settings
from ..designations import from_greysheet_name, with_designation
from ..models import Coin
from ..series import BY_SLUG
from .details import price_grade

PROD_URL = "https://cpgpublicapiv2.greysheet.com/api"
SANDBOX_URL = "https://cpgpublicapiv2beta.greysheet.com/api"


class PricingError(Exception):
    pass


def _money(v) -> Decimal | None:
    if v in (None, ""):
        return None
    s = re.sub(r"[^0-9.]", "", str(v))
    try:
        return Decimal(s) if s else None
    except InvalidOperation:
        return None


def client() -> httpx.Client:
    s = get_settings()
    if not (s.greysheet_api_key and s.greysheet_api_token):
        raise PricingError("GREYSHEET_API_KEY and GREYSHEET_API_TOKEN must be set in .env")
    return httpx.Client(
        base_url=SANDBOX_URL if s.greysheet_use_sandbox else PROD_URL,
        timeout=30,
        headers={"x-api-key": s.greysheet_api_key, "x-api-token": s.greysheet_api_token, "Accept": "application/json"},
    )


def get(c: httpx.Client, path: str, **params) -> list[dict]:
    """GET an endpoint and return its `Data` list, raising PricingError on API-level errors."""
    params = {k: v for k, v in params.items() if v is not None}
    params.setdefault("ApiLevel", "basic")
    r = c.get(path, params=params)
    if r.status_code in (401, 403):
        raise PricingError(
            f"Greysheet rejected the credentials ({r.status_code}). "
            "Check the key/token, and GREYSHEET_USE_SANDBOX if they are sandbox credentials."
        )
    r.raise_for_status()
    body = r.json()
    if body.get("ErrorText"):
        raise PricingError(body["ErrorText"])
    data = body.get("Data") or []
    # Catalog (node) calls on the Basic tier come back with PermitAccess=false but still carry
    # the data, with advanced-only fields blanked out. Only treat it as denied when nothing came back.
    if body.get("PermitAccess") is False and not data and body.get("AccessDeniedMessage"):
        raise PricingError(body["AccessDeniedMessage"])
    return data


def is_set(coin: Coin) -> bool:
    ct = getattr(coin, "coin_type", None)
    s = BY_SLUG.get(ct.slug) if ct else None
    return bool(s and s.is_set)


def _pick(items: list[dict], coin: Coin) -> dict | None:
    """Choose the price row for the coin's grade, preferring a CAC row for CAC coins. Mint and proof sets have
    one price, at Greysheet's "OGP" grade."""
    if is_set(coin):
        rows = [i for i in items if not i.get("IsCac") and _money(i.get("CpgVal")) is not None]
        return next((i for i in rows if str(i.get("GradeLabel") or "").upper().startswith("OGP")), rows[0] if rows else None)
    grade = price_grade(coin)
    # Rows without a CPG are no use (saving one would show the coin as unpriced).
    rows = [i for i in items if str(i.get("Grade")) == str(grade) and _money(i.get("CpgVal")) is not None]
    if not rows:
        return None
    label_plus = [r for r in rows if "+" in str(r.get("GradeLabel") or "")]
    label_plain = [r for r in rows if "+" not in str(r.get("GradeLabel") or "")]
    # A plus coin takes the plus price, else the plain one (conservative); a plain coin never takes a plus price.
    rows = (label_plus or label_plain) if coin.grade_plus and not getattr(coin, "details", False) else label_plain
    cac_rows = [r for r in rows if r.get("IsCac")]
    plain_rows = [r for r in rows if not r.get("IsCac")]
    if coin.cac and cac_rows:
        return cac_rows[0]
    # A coin without a CAC sticker never takes a CAC price.
    return plain_rows[0] if plain_rows else None


def require_grade(coin: Coin) -> None:
    if is_set(coin):
        return  # priced in OGP, no grade
    if not price_grade(coin):
        if coin.grading_service == "RAW":
            raise PricingError("CPG prices are by numeric grade. Give this raw coin a number (e.g. AU55) to look one up.")
        raise PricingError("This coin needs a numeric grade to look up CPG.")


def sheet_key(coin: Coin, gsid: int | None) -> str:
    return f"gsid:{gsid}" if gsid else f"pcgs:{coin.pcgs_number}"


def fetch_cpg(coin: Coin, gsid: int | None = None, cached: dict | None = None) -> dict:
    """Return {'value', 'grade_used', 'description', 'raw', 'greysheet_value', 'sheet'} for the coin's current price.

    `sheet` holds CPG for every grade of the issue (same single API call).

    `greysheet_value` (wholesale) is only filled on Greysheet's Advanced API tier; on Basic it's None.

    Looks up by the coin's PCGS number, or by Greysheet id when the catalog entry has no PCGS number.
    `cached` is a recent all-grades response for the same issue (see grade_prices.recent_entry): no API call.
    """
    if not (coin.pcgs_number or gsid):
        raise PricingError("This coin needs a PCGS number to look up CPG.")
    require_grade(coin)

    if cached is not None:
        data = [cached]
    else:
        with client() as c:
            # No grade: Greysheet returns every grade in this one call, which also feeds the price-by-grade table.
            data = get(
                c,
                "/GetPricingRequest",
                PcgsNumber=None if gsid else coin.pcgs_number,
                Gsid=gsid,
            )
    ident = f"Greysheet id {gsid}" if gsid else f"PCGS #{coin.pcgs_number}"
    if not data:
        raise PricingError(f"Greysheet has no pricing for {ident}")
    entry = data[0]
    row = _pick(entry.get("PricingData") or [], coin)
    if row is None:
        raise PricingError(f"No CPG price for {coin.grade_prefix or ''}{price_grade(coin)} on {ident}")

    designation = from_greysheet_name(entry.get("Name"))
    label = with_designation(str(row.get("GradeLabel") or row.get("Grade")), designation)
    if row.get("IsCac"):
        label += " CAC"
    return {
        "value": _money(row.get("CpgVal")),
        "grade_used": label,
        "description": entry.get("Name"),
        "raw": {"row": row, "gsid": entry.get("GsId"), "name": entry.get("Name")},
        "greysheet_value": _money(row.get("GreyVal")),
        "sheet": sheet_from_entry(sheet_key(coin, gsid), entry),
    }


def sheet_from_entry(key: str, entry: dict) -> dict:
    """Every grade's CPG (and CAC CPG) from one Greysheet pricing response, for saving as a price sheet."""
    return {
        "key": key,
        "gsid": entry.get("GsId"),
        "name": entry.get("Name"),
        "designation": from_greysheet_name(entry.get("Name")),
        "rows": [
            {"grade": r.get("Grade"), "label": str(r.get("GradeLabel") or r.get("Grade")), "cac": bool(r.get("IsCac")),
             "cpg": str(v) if (v := _money(r.get("CpgVal"))) is not None else None,
             "grey": str(g) if (g := _money(r.get("GreyVal"))) is not None else None}
            for r in entry.get("PricingData") or []
        ],
    }


def fetch_sheet(pcgs_number: str | None = None, gsid: int | None = None) -> dict:
    """All grades for one issue (one API call), without needing a coin."""
    with client() as c:
        data = get(c, "/GetPricingRequest", PcgsNumber=None if gsid else pcgs_number, Gsid=gsid)
    if not data:
        raise PricingError(f"Greysheet has no pricing for {'Greysheet id ' + str(gsid) if gsid else 'PCGS #' + str(pcgs_number)}")
    return sheet_from_entry(f"gsid:{gsid}" if gsid else f"pcgs:{pcgs_number}", data[0])

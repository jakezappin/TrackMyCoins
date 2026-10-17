"""Greysheet / CDN Public API v2: catalog browsing and CPG retail pricing.

Overview: https://publicapiv2.greysheet.com/
Spec:     https://cpgpublicapiv2beta.greysheet.com/openapi
Auth: x-api-key + x-api-token headers. The Basic tier returns CpgVal.
"""

import re
from decimal import Decimal, InvalidOperation

import httpx

from ..config import get_settings
from ..models import Coin

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


def _pick(items: list[dict], coin: Coin) -> dict | None:
    """Choose the price row for the coin's grade, preferring a CAC row for CAC coins."""
    rows = [i for i in items if str(i.get("Grade")) == str(coin.grade)]
    if not rows:
        return None
    label_plus = [r for r in rows if "+" in str(r.get("GradeLabel") or "")]
    label_plain = [r for r in rows if "+" not in str(r.get("GradeLabel") or "")]
    rows = (label_plus or label_plain) if coin.grade_plus else (label_plain or rows)
    cac_rows = [r for r in rows if r.get("IsCac")]
    plain_rows = [r for r in rows if not r.get("IsCac")]
    if coin.cac and cac_rows:
        return cac_rows[0]
    return (plain_rows or rows)[0]


def require_grade(coin: Coin) -> None:
    if not coin.grade:
        if coin.grading_service == "RAW":
            raise PricingError("CPG prices are by numeric grade. Give this raw coin a number (e.g. AU55) to look one up.")
        raise PricingError("This coin needs a numeric grade to look up CPG.")


def fetch_cpg(coin: Coin, gsid: int | None = None) -> dict:
    """Return {'value', 'grade_used', 'description', 'raw', 'greysheet_value', 'sheet'} for the coin's current price.

    `sheet` holds CPG for every grade of the issue (same single API call).

    `greysheet_value` (wholesale) is only filled on Greysheet's Advanced API tier; on Basic it's None.

    Looks up by the coin's PCGS number, or by Greysheet id when the catalog entry has no PCGS number.
    """
    if not (coin.pcgs_number or gsid):
        raise PricingError("This coin needs a PCGS number to look up CPG.")
    require_grade(coin)

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
        raise PricingError(f"No CPG price for grade {coin.grade} on {ident}")

    label = str(row.get("GradeLabel") or row.get("Grade"))
    if row.get("IsCac"):
        label += " CAC"
    return {
        "value": _money(row.get("CpgVal")),
        "grade_used": label,
        "description": entry.get("Name"),
        "raw": {"row": row, "gsid": entry.get("GsId"), "name": entry.get("Name")},
        "greysheet_value": _money(row.get("GreyVal")),
        "sheet": {
            "key": f"gsid:{gsid}" if gsid else f"pcgs:{coin.pcgs_number}",
            "gsid": entry.get("GsId"),
            "name": entry.get("Name"),
            "rows": [
                {"grade": r.get("Grade"), "label": str(r.get("GradeLabel") or r.get("Grade")), "cac": bool(r.get("IsCac")),
                 "cpg": str(v) if (v := _money(r.get("CpgVal"))) is not None else None}
                for r in entry.get("PricingData") or []
            ],
        },
    }

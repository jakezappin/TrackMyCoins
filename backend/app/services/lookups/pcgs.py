"""PCGS Public API. Docs: https://www.pcgs.com/publicapi/documentation (1,000 calls/day)."""

import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from .. import quota

from ...config import get_settings
from ...designations import from_pcgs, with_designation
from ...schemas import LookupResult
from ...urls import absolute_url
from .base import LookupError, normalize_mint_mark, over_variety, parse_grade, set_designation, year_of

BASE_URL = "https://api.pcgs.com/publicapi"


def _client() -> httpx.Client:
    token = get_settings().pcgs_api_token
    if not token:
        raise LookupError("PCGS_API_TOKEN is not set in .env")
    return httpx.Client(
        base_url=BASE_URL,
        timeout=20,
        headers={"Authorization": f"bearer {token}", "Accept": "application/json"},
    )


def _get(client: httpx.Client, path: str, **params) -> dict:
    r = client.get(path, params=params or None)
    if r.status_code == 401:
        raise LookupError("PCGS rejected the API token (401). Check PCGS_API_TOKEN.")
    if r.status_code == 429:
        # Over PCGS's daily allowance: pause all PCGS calls until it says to try again, and say when that is.
        try:
            wait = float(r.headers.get("retry-after") or 0)
        except ValueError:
            wait = 0
        wait = wait or 6 * 3600
        quota.pause("pcgs", wait)
        raise LookupError(quota.paused_message("pcgs", wait))
    r.raise_for_status()
    return r.json()


def lookup(cert: str) -> LookupResult:
    with _client() as client:
        facts = _get(client, f"/coindetail/GetCoinFactsByCertNo/{cert}", retrieveAllData="true")
        if not facts.get("IsValidRequest", True) or not facts.get("PCGSNo"):
            raise LookupError(facts.get("ServerMessage") or f"PCGS cert {cert} not found")
        images = []
        try:
            img = _get(client, "/coindetail/GetImagesByCertNo", certNo=cert)
            images = [i["Url"] for i in img.get("Images") or [] if i.get("Url")]
        except (httpx.HTTPError, LookupError, KeyError):
            pass

    if not images:
        images = [i.get("Fullsize") for i in facts.get("Images") or [] if i.get("Fullsize")]

    res = LookupResult(
        grading_service="PCGS",
        cert_number=cert,
        year=year_of(facts.get("Year")) or year_of(facts.get("Name")),
        mint_mark=normalize_mint_mark(facts.get("MintMark")),
        variety=over_variety(facts.get("Name")) or over_variety(str(facts.get("Year") or "")),
        pcgs_number=str(facts["PCGSNo"]),
        description=facts.get("Name"),
        image_urls=images[:10],
        verify_url=f"https://www.pcgs.com/cert/{cert}",
        raw=facts,
    )
    grade = str(facts.get("Grade") or "")
    parse_grade(grade, res)
    # PCGS gives the designation three ways, sometimes only partly in each: the Designation field ("DC", "RD"),
    # the end of the grade ("PR65DC", "MS64DM") and the name ("1937 1C, CAM"). Merge them all.
    set_designation(facts.get("Designation"), res)
    tail = re.match(r"^\s*[A-Z]{1,3}\s*\d{1,2}\+?\s*([A-Z]{2,4})\s*$", grade.upper())
    if tail:
        set_designation(tail.group(1), res)
    if not res.details:
        # Only the name's parts after the first comma ("1895-O $1, DMPL"), and not variety numbers ("FS-101",
        # "DDO FS-801", "VAM-3": FS-101 isn't Full Steps).
        rest = ",".join(str(facts.get("Name") or "").split(",")[1:])
        rest = re.sub(r"\b(?:FS|DDO|DDR|RPM|OMM|VAM|FS-\d+)[-\s]?\d[\w./-]*", " ", rest, flags=re.I)
        set_designation(rest, res)
    vam = facts.get("DieVariety") or facts.get("MinorVariety")
    if vam and "VAM" in str(vam).upper():
        res.vam = str(vam)
    try:
        if facts.get("PriceGuideValue"):
            res.price_guide_value = Decimal(str(facts["PriceGuideValue"]))
    except InvalidOperation:
        pass
    return res


def _sale_date(text: str | None) -> str | None:
    """PCGS auction dates look like '06-2026'; return '2026-06' so they sort and chart."""
    m = re.match(r"^\s*(\d{1,2})[-/](\d{4})", text or "")
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.match(r"^\s*(\d{4})-(\d{2})", text or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def coin_facts(facts: dict) -> dict:
    """Mintage and specifications from a PCGS CoinFacts response (by grade or by cert)."""
    mintage = _num(facts.get("Mintage"))
    return {
        "mintage": int(mintage) if mintage else None,
        "mint_location": (facts.get("MintLocation") or "").strip() or None,
        "metal": (facts.get("MetalContent") or "").strip() or None,
        "weight_g": _num(facts.get("Weight")),
        "diameter_mm": _num(facts.get("Diameter")),
        "edge": (facts.get("Edge") or "").strip() or None,
        "designer": (facts.get("Designer") or "").strip() or None,
        "series": (facts.get("SeriesName") or "").strip() or None,
    }


def sale_from_apr(a: dict) -> dict | None:
    """One auction record from GetAPRByGrade, or None if it has no date or price."""
    date = _sale_date(a.get("Date"))
    if not date or a.get("Price") in (None, ""):
        return None
    return {
        "date": date,
        "price": str(a["Price"]),
        "auctioneer": a.get("Auctioneer") or None,
        "sale_name": a.get("SaleName") or None,
        "lot": str(a.get("LotNumV2") or a.get("LotNo") or "") or None,
        "url": absolute_url(a.get("AuctionLotUrl")),
        "service": a.get("Service") or None,
        "cert_number": a.get("CertNo") or None,
        "cac": bool(a.get("IsCAC")),
    }


def market(pcgs_number: str, grade: int, plus: bool = False, auctions: int = 10) -> dict:
    """PCGS Price Guide value, population and the most recent auction sales for a PCGS # and grade."""
    params = {"PCGSNo": pcgs_number, "GradeNo": grade, "PlusGrade": "true" if plus else "false"}
    with _client() as client:
        facts = _get(client, "/coindetail/GetCoinFactsByGrade", **params)
        if not facts.get("IsValidRequest", True):
            raise LookupError(facts.get("ServerMessage") or f"PCGS has no data for #{pcgs_number} in grade {grade}")
        apr = _get(client, "/coindetail/GetAPRByGrade", **params, NumberOfRecords=auctions)

    sales = [x for x in (sale_from_apr(a) for a in apr.get("Auctions") or []) if x]
    sales.sort(key=lambda s: s["date"], reverse=True)

    guide = facts.get("PriceGuideValue")
    return {
        "facts": coin_facts(facts),
        "pcgs_number": str(pcgs_number),
        "grade": with_designation(facts.get("Grade") or f"{grade}{'+' if plus else ''}", from_pcgs(facts)),
        "price_guide": str(guide) if guide not in (None, "", 0) else None,
        "population": facts.get("Population"),
        "pop_higher": facts.get("PopHigher"),
        "coinfacts_url": absolute_url(facts.get("CoinFactsLink")),
        "auctions": sales[:auctions],
    }


# PCGS allows 1,000 calls a day and each market lookup costs 2, so one issue + grade is fetched at most once a day
# (several coins of the same issue and grade, refreshes, repeat clicks). In memory: the server restarts often.
MARKET_TTL = 24 * 60 * 60
_market_cache: dict[tuple, tuple[float, dict]] = {}


def market_cached(pcgs_number: str, grade: int, plus: bool = False, before_call=None) -> tuple[dict, bool]:
    """(market data, whether PCGS was called). `before_call` runs only when PCGS will really be called (to
    charge the daily allowance; it may raise to stop the call)."""
    key = (str(pcgs_number), int(grade), bool(plus))
    hit = _market_cache.get(key)
    if hit and time.time() - hit[0] < MARKET_TTL:
        return hit[1], False
    if before_call is not None:
        before_call()
    data = {**market(pcgs_number, grade, plus), "fetched_at": datetime.now(timezone.utc).isoformat()}
    _market_cache[key] = (time.time(), data)
    return data, True

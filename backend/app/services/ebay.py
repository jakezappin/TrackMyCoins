"""Current eBay listings for a coin (Browse API). Asking prices of active listings, not sales.

eBay's sold-listings API (Marketplace Insights) needs separate approval; this uses the open Browse API with an
application token (client credentials), which the app requests and renews itself.
"""

import base64
import re
import statistics
import threading
import time
from urllib.parse import urlencode

import httpx

from ..config import get_settings
from ..models import Coin

API = "https://api.ebay.com"
SCOPE = "https://api.ebay.com/oauth/api_scope"
US_COINS = "253"  # eBay category "Coins: US"
CACHE_SECONDS = 30 * 60

_lock = threading.Lock()
_token: dict = {"value": None, "expires": 0.0}
_cache: dict[str, tuple[float, dict]] = {}

SERVICE_WORDS = {"PCGS": ["PCGS"], "NGC": ["NGC"], "ANACS": ["ANACS"], "CACG": ["CACG", "CAC GRADING"]}
# Titles that aren't a graded example of the coin at all.
EXCLUDE = re.compile(
    r"\b(replica|copy|tribute|lot of|lots?|rolls?|sets?|\d+\s*coins?|"
    r"(?:\d+\s*)?pcs|pieces|bags?|uncertified|raw)\b",
    re.I,
)
# Problem coins: refused for a straight-graded coin, required for a Details one.
PROBLEM = re.compile(r"\b(details?|genuine|cleaned|damaged|holed|scratched|environmental|tooled|bent)\b", re.I)
# NGC's names for the same designations: UCAM is PCGS's DCAM, DPL is DMPL.
SAME = {"UCAM": "DCAM", "DPL": "DMPL"}
DESIGNATIONS = ["DMPL", "DPL", "PL", "DCAM", "UCAM", "CAM", "RD", "RB", "BN", "FB", "FBL", "FS", "FH", "FT"]


class EbayError(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.ebay_client_id and s.ebay_client_secret)


def _app_token(client: httpx.Client) -> str:
    with _lock:
        if _token["value"] and time.time() < _token["expires"] - 60:
            return _token["value"]
        s = get_settings()
        basic = base64.b64encode(f"{s.ebay_client_id}:{s.ebay_client_secret}".encode()).decode()
        r = client.post(
            f"{API}/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        if r.status_code != 200:
            raise EbayError("eBay didn't accept the app's keys. Check EBAY_CLIENT_ID / EBAY_CLIENT_SECRET.")
        body = r.json()
        _token.update(value=body["access_token"], expires=time.time() + int(body.get("expires_in", 7200)))
        return _token["value"]


def _date(c: Coin) -> str:
    return f"{c.year}" if c.mint_mark == "P" else f"{c.year}-{c.mint_mark}"


def query_for(c: Coin) -> str:
    """e.g. '1881-S Morgan Dollar PCGS MS65 DMPL'."""
    parts = [_date(c), c.coin_type.name]
    if c.variety and "/" in c.variety:  # overdates / over-mintmarks are part of what's being bought
        parts.append(c.variety.split(",")[0].strip())
    if c.grading_service != "RAW":
        parts.append(c.grading_service)
        if c.grade:
            parts.append(f"{c.grade_prefix or ''}{c.grade}")
    if c.strike_designation:
        parts.append(c.strike_designation)
    return " ".join(parts)


def search_url(q: str) -> str:
    return "https://www.ebay.com/sch/i.html?" + urlencode({"_nkw": q, "_sacat": US_COINS})


def _matches(c: Coin, title: str) -> bool:
    """Keep listings that really are this date, mint, service and grade (titles are free text)."""
    t = title.upper()
    if EXCLUDE.search(title):
        return False
    if bool(PROBLEM.search(title)) != bool(getattr(c, "details", False)):
        return False
    # Date and mint: "1881-S", "1881 S", "1881S"; a P coin must not show another mint mark.
    if c.mint_mark == "P":
        if not re.search(rf"\b{c.year}\b(?!\s*-?\s*(?:CC|[DSOW])\b)", t):
            return False
    elif not re.search(rf"\b{c.year}\s*-?\s*{re.escape(c.mint_mark)}\b", t):
        return False
    if c.grading_service == "RAW":
        return not any(w in t for ws in SERVICE_WORDS.values() for w in ws)
    if not any(w in t for w in SERVICE_WORDS.get(c.grading_service, [c.grading_service])):
        return False
    if c.grade:
        prefix = (c.grade_prefix or "").upper()
        prefixes = {"PR": "(?:PR|PF)"}.get(prefix, re.escape(prefix)) if prefix else "[A-Z]{0,3}"
        # MS64 and MS64+ are priced apart: a plus coin needs the "+", a plain one must not have it.
        plus = r"\s*\+" if c.grade_plus else r"(?!\s*\+)"
        if not re.search(rf"\b{prefixes}\s*-?\s*{c.grade}(?!\d){plus}", t):
            return False
    # Strike designations change the price a lot: require the coin's, refuse others.
    wanted = {SAME.get(w, w) for w in (c.strike_designation or "").upper().split()}
    found = {SAME.get(d, d) for d in DESIGNATIONS if re.search(rf"\b{d}\b", t)}
    if wanted - found:
        return False
    extra = found - wanted
    if extra & {"DMPL", "DPL", "PL", "DCAM", "UCAM", "CAM"}:
        return False
    return True


def _money(m: dict | None) -> float | None:
    try:
        return float(m["value"]) if m and m.get("currency", "USD") == "USD" else None
    except (KeyError, TypeError, ValueError):
        return None


def listings_for(c: Coin) -> dict:
    if not configured():
        raise EbayError("eBay isn't set up on this server yet.")
    q = query_for(c)
    hit = _cache.get(q)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with httpx.Client(timeout=20) as client:
        token = _app_token(client)
        r = client.get(
            f"{API}/buy/browse/v1/item_summary/search",
            params={"q": q, "category_ids": US_COINS, "limit": "100",
                    "filter": "buyingOptions:{FIXED_PRICE|AUCTION},priceCurrency:USD"},
            headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        )
        if r.status_code == 401:
            _token.update(value=None, expires=0)
            raise EbayError("eBay rejected the app token. Try again in a moment.")
        if r.status_code == 429:
            raise EbayError("eBay's daily limit was reached. Try again later.")
        if r.status_code != 200:
            raise EbayError(f"eBay search failed ({r.status_code}).")
        data = r.json()

    items = []
    for it in data.get("itemSummaries") or []:
        title = it.get("title") or ""
        if not _matches(c, title):
            continue
        options = it.get("buyingOptions") or []
        auction = "AUCTION" in options
        price = _money(it.get("currentBidPrice")) if auction else None
        price = price if price is not None else _money(it.get("price"))
        if price is None:
            continue
        items.append({
            "title": title,
            "price": round(price, 2),
            "kind": "auction" if auction and "FIXED_PRICE" not in options else "buy_it_now",
            "best_offer": "BEST_OFFER" in options,
            "bids": it.get("bidCount"),
            "ends": it.get("itemEndDate"),
            "url": it.get("itemWebUrl"),
            "image": (it.get("image") or {}).get("imageUrl"),
            "cac": bool(re.search(r"\bCAC\b", title, re.I)) and c.grading_service != "CACG",
        })
    items.sort(key=lambda x: x["price"])
    fixed = [x["price"] for x in items if x["kind"] == "buy_it_now"]
    result = {
        "query": q,
        "search_url": search_url(q),
        "total_found": data.get("total", len(data.get("itemSummaries") or [])),
        "items": items[:25],
        "stats": {
            "count": len(items),
            "buy_it_now_count": len(fixed),
            "low": min(fixed) if fixed else None,
            "median": round(statistics.median(fixed), 2) if fixed else None,
            "high": max(fixed) if fixed else None,
        },
        "fetched_at": time.time(),
    }
    _cache[q] = (time.time(), result)
    return result

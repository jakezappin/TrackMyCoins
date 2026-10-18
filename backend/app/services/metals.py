"""Melt value: precious-metal content (from PCGS's weight and composition) times live spot prices."""

import logging
import re
import threading
import time

import httpx

log = logging.getLogger(__name__)

TROY_OZ_G = 31.1034768
SPOT_URL = "https://api.gold-api.com/price/{symbol}"  # free, no key
SYMBOLS = {"gold": "XAU", "silver": "XAG", "platinum": "XPT", "palladium": "XPD", "copper": "HG"}  # copper: USD/lb
CACHE_SECONDS = 15 * 60
FAIL_SECONDS = 5 * 60

_lock = threading.Lock()
_spot: dict[str, tuple[float, float | None, str | None]] = {}  # metal -> (checked_at, price, updated_at)

_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(gold|silver|platinum|palladium)\b", re.I)
_FINE = re.compile(r"(?:\.(\d{3,4})|(\d{2}(?:\.\d+)?)%?)\s*(?:fine\s+)?(gold|silver|platinum|palladium)\b", re.I)


def fineness(composition: str | None) -> dict[str, float]:
    """Share of each precious metal: '90% Silver, 10% Copper' -> {'silver': 0.9};
    '.999 Silver' -> {'silver': 0.999}; '91.67% Gold, 3% Silver, 5.33% Copper' -> gold .9167 + silver .03.
    Unclear text (e.g. clad layers with different percentages) gives {} rather than a wrong number."""
    if not composition:
        return {}
    text = composition.strip()
    out: dict[str, float] = {}
    for pct, metal in _PCT.findall(text):
        metal = metal.lower()
        if metal in out:  # the same metal listed twice (clad layers): can't tell the overall share
            return {}
        out[metal] = float(pct) / 100
    if out:
        return out if all(0 < v <= 1 for v in out.values()) else {}
    m = _FINE.search(text)  # ".999 Silver", ".9999 Fine Gold"
    if m and m.group(1):
        return {m.group(3).lower(): float("0." + m.group(1))}
    # "999 Fine Silver", "Silver .999", "Gold 9999"
    m = re.search(r"\b(\d{3,4})\s*(?:fine\s+)?(gold|silver|platinum|palladium)\b", text, re.I) or \
        re.search(r"\b(gold|silver|platinum|palladium)\s*,?\s*\.?(\d{3,4})\b", text, re.I)
    if m:
        digits, metal = (m.group(1), m.group(2)) if m.group(1).isdigit() else (m.group(2), m.group(1))
        share = int(digits) / (10 ** len(digits))
        return {metal.lower(): share} if 0 < share <= 1 else {}
    return {}


def _fetch_spot(metal: str) -> tuple[float | None, str | None]:
    try:
        r = httpx.get(SPOT_URL.format(symbol=SYMBOLS[metal]), timeout=5)
        r.raise_for_status()
        body = r.json()
        price = float(body["price"])
        return (price if price > 0 else None), body.get("updatedAt")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        log.warning("Spot price for %s unavailable: %s", metal, e)
        return None, None


def spot(metal: str) -> tuple[float | None, str | None]:
    """(USD per troy ounce, when it was updated), cached for 15 minutes."""
    with _lock:
        hit = _spot.get(metal)
        now = time.time()
        if hit and now - hit[0] < (CACHE_SECONDS if hit[1] else FAIL_SECONDS):
            return hit[1], hit[2]
    price, updated = _fetch_spot(metal)
    with _lock:
        last = _spot.get(metal)
        if price is None and last and last[1] is not None:
            # Keep the last good price rather than blanking every value; try again after FAIL_SECONDS.
            _spot[metal] = (time.time() - CACHE_SECONDS + FAIL_SECONDS, last[1], last[2])
            return last[1], last[2]
        _spot[metal] = (time.time(), price, updated)
    return price, updated


def melt(weight_g: float | None, composition: str | None) -> dict | None:
    """{'value', 'metals': [{'metal', 'oz', 'spot'}], 'as_of'} or None for base-metal coins / missing data."""
    shares = fineness(composition)
    if not weight_g or not shares:
        return None
    metals, total, as_of = [], 0.0, None
    for metal, share in shares.items():
        oz = weight_g * share / TROY_OZ_G
        price, updated = spot(metal)
        if price is None:
            return None
        metals.append({"metal": metal, "oz": round(oz, 4), "spot": round(price, 2)})
        total += oz * price
        as_of = as_of or updated
    return {"value": round(total, 2), "metals": metals, "as_of": as_of}

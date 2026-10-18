"""CAC sticker lookup via the public page at cacgrading.com/lookup/{cert}.

There is no public API. The page is server-rendered HTML; parsing is best-effort and
may need adjusting if CAC changes the page. Unknown certs redirect back to /lookup.
"""

import re

import httpx
from bs4 import BeautifulSoup

from .base import LookupError

LOOKUP_URL = "https://www.cacgrading.com/lookup/{cert}"


def check_sticker(cert: str) -> dict:
    """Return {'cac': bool, 'sticker': 'green'|'gold'|None, 'verify_url': str, 'text': str}."""
    url = LOOKUP_URL.format(cert=re.sub(r"[^0-9A-Za-z]", "", cert))
    with httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": "coin-app/0.1"}) as client:
        r = client.get(url)
    if r.status_code in (301, 302, 303, 307, 308):
        # Not found in CAC's database.
        return {"cac": False, "sticker": None, "verify_url": url, "text": ""}
    if r.status_code != 200:
        raise LookupError(f"CAC lookup failed ({r.status_code})")

    return parse_page(r.text, url)


# The color counts only next to the sticker: "Gold CAC sticker", "Green bean", "Sticker: Gold". A bare "Gold"
# elsewhere (the site menu's "Gold coins", a $20 gold piece's description) says nothing about the sticker.
_NEAR_TEXT = [
    re.compile(r"\b(gold|green)\s+(?:cac\s+)?(?:sticker|bean|label)\b"),
    re.compile(r"\b(?:sticker|bean|label)\s*(?:colou?r|type)?\s*[:\-]?\s*(gold|green)\b"),
]
_NEAR_MARKUP = re.compile(r"(gold|green)[-_ ]?(?:sticker|bean|label)|(?:sticker|bean|label)[-_ ]?(gold|green)")


def parse_page(html: str, url: str = "") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "noscript"]):
        tag.decompose()  # menus and page chrome mention "Gold" and "Green" for other reasons
    main = soup.find("main") or soup.body or soup
    text = " ".join(main.get_text(" ").split())
    lowered = text.lower()

    sticker = None
    for pattern in _NEAR_TEXT:
        m = pattern.search(lowered)
        if m:
            sticker = m.group(1)
            break
    if sticker is None:
        # Image names and classes inside the result: <img src="/img/gold-sticker.png">, class="green-bean".
        for el in main.find_all(True):
            attrs = " ".join(str(v) for k, v in el.attrs.items() if k in ("src", "class", "alt", "title", "id")).lower()
            m = _NEAR_MARKUP.search(attrs)
            if m:
                sticker = m.group(1) or m.group(2)
                break

    not_found = any(p in lowered for p in ("not found", "no results", "not been approved", "did not"))
    return {"cac": sticker is not None or not not_found, "sticker": sticker, "verify_url": url, "text": text[:2000]}

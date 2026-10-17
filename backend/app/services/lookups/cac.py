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

    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.find("main") or soup.body or soup
    text = " ".join(main.get_text(" ").split())
    lowered = text.lower()

    sticker = None
    # Look for the sticker color in text and in image/class names.
    markup = r.text.lower()
    if re.search(r"\bgold\b", lowered) or re.search(r"gold[-_ ]?(sticker|bean|label)", markup):
        sticker = "gold"
    elif re.search(r"\bgreen\b", lowered) or re.search(r"green[-_ ]?(sticker|bean|label)", markup):
        sticker = "green"

    not_found = any(p in lowered for p in ("not found", "no results", "not been approved", "did not"))
    return {"cac": sticker is not None or not not_found, "sticker": sticker, "verify_url": url, "text": text[:2000]}

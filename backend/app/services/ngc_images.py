"""NGC coin photos.

NGC's cert pages are behind bot protection, but the photos themselves are public files on Amazon S3:
  https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/<folder id>/NGC<cert>_OBV@500x722.jpg
The folder id is random, so the link has to come from NGC's page itself (the "Add to TrackMyCoins" bookmark
collects it); from one link we get both sides at full size by swapping OBV/REV and dropping the @WxH suffix.
"""

import re

HOST = "ccg-imaging-ngc-coins-production.s3.amazonaws.com"
LINK = re.compile(
    r"^https?://" + re.escape(HOST) + r"/(?P<folder>[0-9a-fA-F-]{36})/NGC(?P<cert>\d{5,10}-\d{3})_(?:OBV|REV)(?:@\d+x\d+)?\.jpe?g(?:\?.*)?$"
)


class NgcImageError(Exception):
    pass


def parse(link: str) -> dict:
    m = LINK.match((link or "").strip())
    if not m:
        raise NgcImageError(
            "That isn't an NGC photo link. On NGC's cert page, right-click (or long-press) the coin photo, "
            "choose Copy Image Address, and paste it here."
        )
    base = f"https://{HOST}/{m['folder'].lower()}/NGC{m['cert']}"
    return {
        "cert_number": m["cert"],
        "urls": [f"{base}_OBV.jpg", f"{base}_REV.jpg"],
        "previews": [f"{base}_OBV@500x722.jpg", f"{base}_REV@500x722.jpg"],
    }

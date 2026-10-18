"""NGC coin photos.

NGC's cert pages are behind bot protection, but the photos themselves are public files on Amazon S3:
  https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/<folder id>/NGC<cert>_OBV@500x722.jpg
The folder id is random (a 36-character UUID on older photos, 40 hex characters on newer ones), so the link has to
come from NGC's page itself: the "Add to TrackMyCoins" bookmark
collects it, or the user pastes one image link. From one link we get both sides at full size by swapping
OBV/REV and dropping the @WxH suffix.
"""

import re

import httpx

HOST = "ccg-imaging-ngc-coins-production.s3.amazonaws.com"
BUCKET = "ccg-imaging-ngc-coins-production"
# As forgiving as possible about the parts NGC varies (folder id length, case, OBV/Obverse, preview size, extension,
# S3 address style), but only ever NGC's own photo bucket: the server fetches these links.
LINK = re.compile(
    r"^https?://(?P<host>" + re.escape(BUCKET) + r"\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com"
    r"|s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com/" + re.escape(BUCKET) + r")"
    r"/(?P<folder>(?:[A-Za-z0-9_-]{1,100}/){0,4})"
    r"(?P<prefix>NGC[_-]?)?(?P<cert>\d{4,12}(?:-\d{1,4})?)[_-]"
    r"(?P<side>obverse|reverse|obv|rev)(?P<size>[@_-]\d{2,5}x\d{2,5})?"
    r"\.(?P<ext>jpe?g|png|webp)(?:[?#].*)?$",
    re.IGNORECASE,
)
# S3 names are case-sensitive, so the other side keeps the pasted link's spelling (_OBV/_REV, _obv/_rev,
# _Obverse/_Reverse). Preview sizes vary (@500x722, @200X300...), so full size is tried first, then the same size.
_OTHER = {"obv": "rev", "rev": "obv", "obverse": "reverse", "reverse": "obverse"}


NO_IMAGES = "The link may be incorrect or no images are available for this coin."


class NgcImageError(Exception):
    pass


def _same_case(word: str, like: str) -> str:
    if like.isupper():
        return word.upper()
    if like[:1].isupper():
        return word.capitalize()
    return word.lower()


def parse(link: str) -> dict:
    link = (link or "").strip().strip("<>\"' ")
    m = LINK.match(link)
    if not m:
        raise NgcImageError(NO_IMAGES)
    side = m["side"]
    other = _same_case(_OTHER[side.lower()], side)
    # Whichever address style was pasted, it's the same bucket: use the standard address (the one photo downloads allow).
    base = f"https://{HOST}/{m['folder']}{m['prefix'] or ''}{m['cert']}_"
    size, ext = m["size"] or "", m["ext"]
    sides = (side, other) if side.lower().startswith("obv") else (other, side)
    full = [f"{base}{sd}.{ext}" for sd in sides]
    sized = [f"{base}{sd}{size}.{ext}" for sd in sides]
    pasted = link.split("?", 1)[0].split("#", 1)[0]
    # Show the pasted (small) image for its side; the other side's preview size isn't known, so use full size.
    previews = [pasted, full[1]] if side.lower().startswith("obv") else [full[0], pasted]
    return {"cert_number": m["cert"], "urls": full, "fallbacks": sized, "previews": previews}


def resolve(link: str) -> dict:
    """Both sides' full-size URLs, keeping only the ones NGC actually has."""
    info = parse(link)
    found, previews = [], []
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        # Each side at full size, or failing that at the pasted link's preview size.
        for candidates, preview in zip(zip(info["urls"], info["fallbacks"]), info["previews"]):
            for url in dict.fromkeys(candidates):
                try:
                    if client.head(url).status_code == 200:
                        found.append(url)
                        previews.append(preview)
                        break
                except httpx.HTTPError:
                    continue
    if not found:
        raise NgcImageError(NO_IMAGES)
    return {**info, "urls": found, "previews": previews}

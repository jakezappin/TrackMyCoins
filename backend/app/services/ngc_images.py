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
# Deliberately forgiving: any link to NGC's photo bucket (any S3 address style) whose file name has the cert number
# and the side in it. Prefixes (TN_ thumbnails), size suffixes (@500x722, _200x300), case and extension all vary
# between coins and over time. Only ever NGC's own bucket, though: the server fetches these links.
_BUCKET_LINK = re.compile(
    r"^https?://(?:" + re.escape(BUCKET) + r"\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com"
    r"|s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com/" + re.escape(BUCKET) + r")/(?P<path>[^?#]+)", re.IGNORECASE)
_CORE = re.compile(r"(?P<core>(?:NGC[_-]?)?(?P<cert>\d{4,12}(?:-\d{1,4})?)[_-]?(?P<side>obverse|reverse|obv|rev))",
                   re.IGNORECASE)
_EXT = re.compile(r"\.(?P<ext>jpe?g|png|webp)$", re.IGNORECASE)
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
    """Both sides' photo URLs from one pasted NGC photo link: full size first (the file name without any thumbnail
    prefix or size suffix), then the pasted file's own name, for each side."""
    link = (link or "").strip().strip("<>\"' ")
    m = _BUCKET_LINK.match(link)
    if not m:
        raise NgcImageError(NO_IMAGES)
    path = m["path"]
    if ".." in path.split("/"):
        raise NgcImageError(NO_IMAGES)
    folder, _, name = path.rpartition("/")
    core, ext = _CORE.search(name), _EXT.search(name)
    if not core or not ext:
        raise NgcImageError(NO_IMAGES)
    side = core["side"]
    other = _same_case(_OTHER[side.lower()], side)
    base = f"https://{HOST}/{folder + '/' if folder else ''}"

    def named(which: str) -> tuple[str, str]:
        """(full-size name, the pasted name) for one side."""
        swap = core["core"][: core.start("side") - core.start("core")] + which
        full = f"{swap}.{ext['ext']}"
        pasted = name[: core.start("core")] + swap + name[core.end("core"):]
        return base + full, base + pasted

    obv_side, rev_side = (side, other) if side.lower().startswith("obv") else (other, side)
    obv, rev = named(obv_side), named(rev_side)
    pasted_url = base + name
    return {
        "cert_number": core["cert"],
        "urls": [obv[0], rev[0]],
        "fallbacks": [obv[1], rev[1]],
        # The pasted (small) image previews its own side; the other side shows full size.
        "previews": [pasted_url, rev[0]] if side.lower().startswith("obv") else [obv[0], pasted_url],
    }


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

"""Read a grading-service slab label from a photo.

1. Barcode first (free and exact): NGC-style certs are used as-is; numeric codes are confirmed with a PCGS
   lookup, which also returns the coin's details.
2. Otherwise Claude reads the printed label (vision + structured output), if an API key is configured.
"""

import base64
import io
import json
import logging
import re

import anthropic
import httpx
import zxingcpp
from PIL import Image, ImageOps

from ..config import get_settings
from . import lookups

log = logging.getLogger(__name__)

try:  # iPhone photos (HEIC) when the browser sends them as-is
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass

MAX_SIDE = 1800  # plenty for label text; keeps the request small


class LabelError(Exception):
    pass


def _nullable(t: str, **extra) -> dict:
    return {"anyOf": [{"type": t, **extra}, {"type": "null"}]}


SCHEMA = {
    "type": "object",
    "properties": {
        "found_label": {"type": "boolean", "description": "A grading-service slab label is visible and readable."},
        "grading_service": {"type": "string", "enum": ["PCGS", "NGC", "ANACS", "CACG", "unknown"]},
        "cert_number": _nullable("string"),
        "year": _nullable("integer"),
        "mint_mark": _nullable("string"),
        "coin_type": _nullable("string"),
        "denomination": _nullable("string"),
        "grade_prefix": _nullable("string"),
        "grade": _nullable("integer"),
        "grade_plus": {"type": "boolean"},
        "grade_star": {"type": "boolean"},
        "strike_designation": _nullable("string"),
        "variety": _nullable("string"),
        "vam": _nullable("string"),
        "cac_sticker": {"type": "string", "enum": ["green", "gold", "none"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": _nullable("string"),
    },
    "required": [
        "found_label", "grading_service", "cert_number", "year", "mint_mark", "coin_type", "denomination",
        "grade_prefix", "grade", "grade_plus", "grade_star", "strike_designation", "variety", "vam",
        "cac_sticker", "confidence", "notes",
    ],
    "additionalProperties": False,
}

PROMPT = """This photo should show a U.S. coin in a third-party grading slab (PCGS, NGC, ANACS or CAC Grading).
Read the slab's printed label and fill in the fields.

- cert_number: the certification number exactly as printed (digits, and a dash if NGC prints one, e.g. "1234567-001"). Not the PCGS coin number or a barcode's other numbers.
- year and mint_mark: from the date, e.g. "1881-S" gives 1881 and "S". No mint mark (Philadelphia) is "P". For a date like "1878 8TF" the year is 1878 and "8TF" is the variety.
- coin_type: the series, e.g. "Morgan Dollar", "Peace Dollar", "Saint-Gaudens $20".
- grade_prefix and grade: e.g. "MS" and 65 for "MS65"; proofs are "PR" (NGC's "PF" is also "PR"). grade_plus for a "+", grade_star for a star (★).
- strike_designation: designations printed with the grade, using these abbreviations: PL, DMPL, DPL, RD, RB, BN, FB, FBL, FS, FH, FT, CAM, DCAM, UCAM. Several are separated by spaces, e.g. "RD CAM".
- variety: any variety or pedigree text (e.g. "8TF", "VAM-3 Hot Lips", "First Strike", "Tail feathers"), or null.
- vam: the VAM number alone if printed, e.g. "VAM-3", else null.
- cac_sticker: "green" or "gold" if a CAC bean sticker is on the slab, else "none".
- If no slab label is readable, set found_label false, leave the other fields null or false, and explain briefly in notes.
Never guess a cert number: if any digit is unreadable, set cert_number null and say so in notes. Set confidence to how sure you are of the cert number and grade."""


BARCODE_SIDE = 3000  # barcodes need more pixels than text
NGC_CERT = re.compile(r"\d{6,10}-\d{3}")
DIGITS = re.compile(r"\d{7,10}")


def _open(data: bytes) -> Image.Image:
    """Any phone photo (HEIC, huge JPEG, rotated) as an upright RGB image."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((BARCODE_SIDE, BARCODE_SIDE))
            return im
    except Exception as e:
        raise LabelError("That file isn't a photo we can read. Try a JPEG or PNG.") from e


def _jpeg_b64(img: Image.Image) -> str:
    img = img.copy()
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return base64.standard_b64encode(out.getvalue()).decode()


def _barcode_texts(img: Image.Image) -> list[str]:
    try:
        return [r.text.strip() for r in zxingcpp.read_barcodes(img) if r.text and r.text.strip()]
    except Exception:  # pragma: no cover - a decoder hiccup shouldn't block the Claude fallback
        log.exception("Barcode decode failed")
        return []


def _blank(**fields) -> dict:
    r = {k: None for k in SCHEMA["properties"]}
    r.update(found_label=True, grade_plus=False, grade_star=False, confidence="high")
    r.update(fields)
    return r


def _from_barcodes(texts: list[str]) -> dict | None:
    """A reading from the slab barcode, or None if it can't be matched to a cert."""
    for t in texts:
        m = NGC_CERT.search(t)
        if m:
            return _blank(grading_service="NGC", cert_number=m.group(0), source="barcode",
                          notes="Cert number read from the NGC barcode.")
    if not get_settings().pcgs_api_token:
        return None
    candidates = list(dict.fromkeys(d for t in texts for d in DIGITS.findall(t)))[:2]  # PCGS allows 1,000 calls/day
    for cert in candidates:
        try:
            found = lookups.lookup("PCGS", cert)
        except (lookups.LookupError, httpx.HTTPError):
            continue
        if found.year is None and found.grade is None:
            continue
        return _blank(
            grading_service="PCGS", cert_number=found.cert_number, year=found.year, mint_mark=found.mint_mark,
            grade_prefix=found.grade_prefix, grade=found.grade, grade_plus=found.grade_plus,
            grade_star=found.grade_star, strike_designation=found.strike_designation, vam=found.vam,
            coin_type=found.description, cac_sticker=found.cac_sticker if found.cac else None,
            source="barcode", lookup=found.model_dump(mode="json"),
            notes="Read from the barcode and confirmed with PCGS.",
        )
    return None


def read_label(data: bytes) -> dict:
    img = _open(data)
    texts = _barcode_texts(img)
    if texts:
        hit = _from_barcodes(texts)
        if hit:
            return hit
    settings = get_settings()
    if not settings.anthropic_api_key:
        if texts:
            raise LabelError("Found a barcode but couldn't match it to a cert. Enter the cert number yourself.")
        raise LabelError(
            "Couldn't find a barcode in that photo. Try a closer, sharper photo of the label's barcode, "
            "or enter the cert number yourself."
        )
    b64 = _jpeg_b64(img)
    result = _ask_claude(
        [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
         {"type": "text", "text": PROMPT}],
        "Try a closer photo of just the label.",
    )
    result["source"] = "claude"
    return result


def _ask_claude(content: list, retry_hint: str) -> dict:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=90.0)
    try:
        response = client.beta.messages.create(
            model=settings.label_model,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.RateLimitError as e:
        raise LabelError("Too many requests right now. Try again in a minute.") from e
    except anthropic.APIStatusError as e:
        log.warning("Claude read failed: %s %s", e.status_code, e.message)
        raise LabelError("Couldn't read the details right now. Try again, or enter them yourself.") from e
    except anthropic.APIConnectionError as e:
        raise LabelError("Couldn't reach the reader. Check the connection and try again.") from e

    if response.stop_reason == "refusal":
        raise LabelError("The reader declined this. Enter the details yourself.")
    if response.stop_reason == "max_tokens":
        raise LabelError(f"Couldn't read the details. {retry_hint}")
    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        result = json.loads(text or "")
    except json.JSONDecodeError as e:
        raise LabelError(f"Couldn't read the details. {retry_hint}") from e
    return _clean(result)


# ---- NGC cert page (sent by the "Add to TrackMyCoins" bookmark from the user's own browser) ----------

NGC_PAGE_PROMPT = """Below is the visible text of an NGC certification verification page for one coin, copied from
the collector's browser. Fill in the fields for that coin. The grading service is NGC and the page is a certification
lookup, so set found_label true if the text describes a coin.

- year and mint_mark from the coin's date, e.g. "1881-S" or "1881 S $1" gives 1881 and "S"; no mint mark is "P".
- coin_type: the series, e.g. "Morgan Dollar".
- grade_prefix and grade from the grade, e.g. "MS 62" gives "MS" and 62. NGC's "PF" proofs are "PR". A "+" sets
  grade_plus; a star (★) sets grade_star.
- strike_designation: designations next to the grade, abbreviated as PL, DPL, DMPL, RD, RB, BN, FB, FBL, FS, FH,
  FT, CAM, DCAM, UCAM (NGC's "Ultra Cameo" is UCAM). Several are separated by spaces.
- variety: variety or pedigree text (e.g. "VAM-3 Hot Lips", "8TF", "Toned"), else null. vam: the VAM number alone.
- cac_sticker: "none" unless the text says the coin has a CAC sticker, then "green" or "gold".
- Ignore navigation, ads, and other coins mentioned on the page.

Page text:
"""

DATE_IN_TEXT = re.compile(r"\b(1[789]\d\d|20[0-4]\d)(?:[\s-]+(CC|[PDSOW]))?\b")
GRADE_IN_TEXT = re.compile(r"\b(MS|PF|PR|SP|AU|XF|EF|VF|F|VG|G|AG|FR|PO)\s?(\d{1,2})(\s?\+)?(\s?(?:★|\*))?", re.I)


def read_ngc_page(cert: str, grade_in_url: str | None, text: str) -> dict:
    """Coin details from NGC's cert page text: Claude when configured, a simple parser otherwise.
    The cert comes from the page address, so it is always trusted over anything in the text."""
    text = (text or "")[:4000]
    result = None
    if get_settings().anthropic_api_key and text.strip():
        try:
            result = _ask_claude([{"type": "text", "text": NGC_PAGE_PROMPT + text}], "")
            result["source"] = "ngc_page"
        except LabelError as e:
            log.warning("NGC page read fell back to the simple parser: %s", e)
    if result is None:
        result = _blank(source="ngc_page", confidence="medium")
        m = DATE_IN_TEXT.search(text)
        if m:
            result["year"], result["mint_mark"] = int(m.group(1)), (m.group(2) or "P").upper()
        g = GRADE_IN_TEXT.search(text)
        if g:
            result["grade_prefix"] = "PR" if g.group(1).upper() in ("PF", "PR") else g.group(1).upper()
            result["grade"] = int(g.group(2))
            result["grade_plus"] = bool(g.group(3))
            result["grade_star"] = bool(g.group(4))
    result.update(found_label=True, grading_service="NGC", cert_number=cert)
    # The grade in NGC's address is the numeric grade; use it when the text didn't give one.
    m = re.fullmatch(r"(\d{1,2})", (grade_in_url or "").strip())
    if result.get("grade") is None and m and 1 <= int(m.group(1)) <= 70:
        result["grade"] = int(m.group(1))
    return result


def _clean(r: dict) -> dict:
    """Tidy values so they drop straight into the coin form."""
    service = r.get("grading_service")
    r["grading_service"] = service if service in ("PCGS", "NGC", "ANACS", "CACG") else None
    for k in ("cert_number", "mint_mark", "grade_prefix", "strike_designation", "variety", "vam", "coin_type",
              "denomination", "notes"):
        v = r.get(k)
        r[k] = v.strip() or None if isinstance(v, str) else None
    if r["cert_number"]:
        r["cert_number"] = r["cert_number"].replace(" ", "")
    if r["mint_mark"]:
        r["mint_mark"] = r["mint_mark"].upper()
    if r["grade_prefix"]:
        r["grade_prefix"] = "PR" if r["grade_prefix"].upper() in ("PF", "PR", "PROOF") else r["grade_prefix"].upper()
    g = r.get("grade")
    r["grade"] = g if isinstance(g, int) and 1 <= g <= 70 else None
    y = r.get("year")
    r["year"] = y if isinstance(y, int) and 1700 <= y <= 2200 else None
    r["cac_sticker"] = r.get("cac_sticker") if r.get("cac_sticker") in ("green", "gold") else None
    return r

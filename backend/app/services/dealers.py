"""Dealer contacts: reading a business card or show banner from a photo, the card photo itself, links to the coins
and bullion bought from or sold to the dealer, and a vCard for the phone's contacts."""

import re
import uuid
from difflib import SequenceMatcher
from pathlib import Path

from PIL import ImageOps

from ..config import get_settings
from ..images import ImageTooLarge, open_image
from ..models import Dealer
from . import label_reader, quota
from .label_reader import LabelError, _jpeg_b64, _nullable

CARD_SIDE = 1600


def _s(**extra) -> dict:
    return _nullable("string", **extra)


SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "Contact details for a business or person are readable."},
        "business": _s(),
        "contact_name": _s(),
        "phone": _s(),
        "email": _s(),
        "website": _s(),
        "address": _s(),
        "social": _s(),
        "specialties": {"type": "array", "items": {"type": "string"}},
        "notes": _s(),
    },
    "required": ["found", "business", "contact_name", "phone", "email", "website", "address", "social",
                 "specialties", "notes"],
    "additionalProperties": False,
}

PROMPT = """This photo should show a coin dealer's business card, or their banner or sign at a coin show. Read the
contact details printed on it.

- business: the company or table name, e.g. "Rick's Rare Coins".
- contact_name: a person's name, if one is printed, without a job title ("Dana Kim", not "Dana Kim, Owner").
- phone: the main phone number as printed (one number; if there are several, prefer mobile or "cell").
- email, website (without "https://"), address (street, city, state, ZIP on one line).
- social: social media handles or pages, e.g. "@ricksrare (Instagram)", several separated by commas.
- specialties: what they say they buy or sell, as short tags, e.g. ["Morgan Dollars", "Gold", "CAC Coins"].
  Leave out generic words like "Coins" or "Buy & Sell".
- notes: other useful printed text, e.g. a booth number, "Member PNG", "ANA Life Member", hours. Else null.
- Copy only what's printed: never guess or complete an email, phone or web address. If nothing readable is a
  contact detail, set found false and the rest null (specialties empty)."""


def _clean(r: dict) -> dict:
    out = {k: (v.strip() if isinstance(v, str) else v) or None for k, v in r.items() if k != "specialties"}
    out["found"] = bool(r.get("found"))
    out["specialties"] = [t.strip() for t in r.get("specialties") or [] if isinstance(t, str) and t.strip()][:12]
    if out.get("website"):
        out["website"] = re.sub(r"^https?://", "", out["website"], flags=re.I).rstrip("/")
    return out


def read_card(data: bytes, user_id: int | None = None) -> dict:
    """Contact details from a photo of a business card or show banner (Claude)."""
    if not get_settings().anthropic_api_key:
        raise LabelError("Reading cards isn't set up on this server. Enter the details yourself.")
    img = _open(data)
    if user_id is not None:
        quota.spend(user_id, "claude")
    return label_reader._ask_claude(
        [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg_b64(img)}},
         {"type": "text", "text": PROMPT}],
        "Try a closer, straighter photo of the card or banner.",
        schema=SCHEMA,
        clean=_clean,
    )


def _open(data: bytes):
    try:
        im = open_image(data, max_side=4000)
        return ImageOps.exif_transpose(im).convert("RGB")
    except ImageTooLarge as e:
        raise LabelError(str(e)) from e
    except Exception as e:
        raise LabelError("That file isn't a photo we can read. Try a JPEG or PNG.") from e


# ---- The card photo -------------------------------------------------------------------------------------------


def photo_dir() -> Path:
    return get_settings().photo_dir / "dealers"


def save_photo(dealer: Dealer, data: bytes) -> None:
    """Keep the card or banner photo (a JPEG, at most CARD_SIDE px, without metadata), replacing any earlier one."""
    if len(data) > get_settings().max_photo_bytes:
        raise LabelError("That photo is too large (15 MB max).")
    img = _open(data)
    img.thumbnail((CARD_SIDE, CARD_SIDE))
    d = photo_dir()
    d.mkdir(parents=True, exist_ok=True)
    name = f"{dealer.id}-{uuid.uuid4().hex[:12]}.jpg"
    img.save(d / name, "JPEG", quality=85, optimize=True)
    delete_photo(dealer)
    dealer.photo_file = name


def delete_photo(dealer: Dealer) -> None:
    if dealer.photo_file:
        (photo_dir() / dealer.photo_file).unlink(missing_ok=True)
        dealer.photo_file = None


# ---- Matching typed names to a dealer ("Link my coins") --------------------------------------------------------


def _norm(text: str | None) -> str:
    t = re.sub(r"[^a-z0-9 ]", "", (text or "").lower().replace("&", " and "))
    t = re.sub(r"\b(inc|llc|ltd|co|the|coins?|numismatics?|rare|company)\b", " ", t)
    return " ".join(t.split())


def name_matches(typed: str | None, dealer: Dealer) -> bool:
    """Whether a typed "Purchased from" / "Sold to" names this dealer: "Ricks Rare Coins" and "Rick's Rare Coins, Inc."
    match "Rick's Rare Coins"; a contact's full name matches too."""
    t = _norm(typed)
    if not t:
        return False
    for name in (dealer.business, dealer.contact_name):
        n = _norm(name)
        if n and (t == n or SequenceMatcher(None, t, n).ratio() >= 0.88 or (len(n) >= 6 and (n in t or t in n))):
            return True
    return False


# ---- vCard --------------------------------------------------------------------------------------------------------


def _v(text: str | None) -> str:
    """Text escaped for a vCard value."""
    out = (text or "").replace("\\", "\\\\")
    for ch in ",;":
        out = out.replace(ch, "\\" + ch)
    return out.replace("\n", "\\n")


def vcard(d: Dealer) -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    full = d.contact_name or d.business or "Dealer"
    parts = full.split()
    last, first = (parts[-1], " ".join(parts[:-1])) if d.contact_name and len(parts) > 1 else (full, "")
    lines += [f"N:{_v(last)};{_v(first)};;;", f"FN:{_v(full)}"]
    if d.business:
        lines.append(f"ORG:{_v(d.business)}")
    if d.phone:
        lines.append(f"TEL;TYPE=WORK,VOICE:{_v(d.phone)}")
    if d.email:
        lines.append(f"EMAIL;TYPE=WORK:{_v(d.email)}")
    if d.website:
        url = d.website if re.match(r"^https?://", d.website, re.I) else f"https://{d.website}"
        lines.append(f"URL:{_v(url)}")
    if d.address:
        lines.append(f"ADR;TYPE=WORK:;;{_v(d.address)};;;;")
    note = "\n".join(x for x in (", ".join(d.specialties or []), d.notes, d.social) if x)
    if note:
        lines.append(f"NOTE:{_v(note)}")
    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"

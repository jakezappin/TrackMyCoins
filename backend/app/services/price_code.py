"""Price codes for labels: a dealer-style letter code that hides a price (or a date) from everyone but the owner.

The owner picks a phrase with exactly 10 different letters, e.g. I LOVE FRANK. Its letters stand for the digits in
order, starting at 0 (I=0 ... K=9) or at 1 (I=1 ... N=9, K=0), whichever the owner uses. Prices are rounded to the
nearest whole dollar (no cents), each digit becomes its letter, and the code is filled out to the owner's code length
with letters that aren't in the phrase, mixed in among the real ones. A reader skips any letter not in the phrase.
Dates are month, day and 2-digit year, coded the same way without filler: 03/15/25 -> "IV LF OF".
"""

import hashlib
import string
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MIN_LENGTH, MAX_LENGTH = 3, 10


class PriceCodeError(ValueError):
    pass


def letters(phrase: str | None) -> list[str]:
    """The phrase's different letters, in order (spaces, punctuation and repeats don't count)."""
    out: list[str] = []
    for ch in (phrase or "").upper():
        if ch in string.ascii_uppercase and ch not in out:
            out.append(ch)
    return out


def check_phrase(phrase: str) -> str:
    """The phrase, tidied; PriceCodeError unless it has exactly 10 different letters."""
    n = len(letters(phrase))
    if n != 10:
        raise PriceCodeError(f"Your phrase has {n} different letter{'s' if n != 1 else ''}. It needs exactly 10.")
    return " ".join(phrase.upper().split())


def _digit_letters(phrase: str, start: int) -> dict[str, str]:
    key = letters(phrase)
    if len(key) != 10 or start not in (0, 1):
        raise PriceCodeError("Set up your price code in Account settings first.")
    return {str((i + start) % 10): ch for i, ch in enumerate(key)}


def whole_dollars(value: Decimal | float | int) -> int:
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def encode_price(value: Decimal | float | int, phrase: str, start: int, length: int, seed: str = "") -> str:
    """The coded price. `seed` (e.g. the coin's id) picks the filler, so reprinting a label gives the same code."""
    to_letter = _digit_letters(phrase, start)
    code = [to_letter[d] for d in str(abs(whole_dollars(value)))]
    filler = [c for c in string.ascii_uppercase if c not in to_letter.values()]
    h = hashlib.sha256(f"{seed}|{''.join(code)}".encode()).digest()
    i = 0
    while len(code) < max(MIN_LENGTH, min(MAX_LENGTH, length)):
        code.insert(h[i] % (len(code) + 1), filler[h[i + 1] % len(filler)])
        i += 2
    return "".join(code)


def encode_date(d: date, phrase: str, start: int) -> str:
    to_letter = _digit_letters(phrase, start)
    return " ".join("".join(to_letter[ch] for ch in part) for part in (f"{d.month:02d}", f"{d.day:02d}", f"{d.year % 100:02d}"))


def decode(code: str, phrase: str, start: int) -> str:
    """The digits a code stands for (filler skipped): for checking codes, and the Account page's examples."""
    to_digit = {v: k for k, v in _digit_letters(phrase, start).items()}
    return "".join(to_digit.get(ch, "") if ch != " " else " " for ch in code.upper()).strip()

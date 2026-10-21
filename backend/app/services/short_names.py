"""Short coin names for the front of a 2x2 flip insert: "Morgan", "Merc", "ASE". Themed coins are named for the
specific coin, from its variety: "Delaware Quarter", "Elgin Comm. Half", "Stone Mountain Comm. Half"."""

import re

SHORT = {
    "half-cents": "Half Cent",
    "large-cents": "Large Cent",
    "flying-eagle-cents": "Flying Eagle",
    "indian-head-cents": "Indian Cent",
    "lincoln-cents": "Lincoln",
    "two-cent-pieces": "2c Piece",
    "three-cent-silver": "Trime",
    "three-cent-nickels": "3c Nickel",
    "shield-nickels": "Shield Nickel",
    "liberty-head-nickels": "V Nickel",
    "buffalo-nickels": "Buffalo",
    "jefferson-nickels": "Jefferson",
    "seated-liberty-half-dimes": "Seated Half Dime",
    "seated-liberty-dimes": "Seated Dime",
    "barber-dimes": "Barber Dime",
    "early-half-dimes": "Early Half Dime",
    "capped-bust-half-dimes": "Bust Half Dime",
    "draped-bust-dimes": "Draped Bust Dime",
    "capped-bust-dimes": "Bust Dime",
    "mercury-dimes": "Merc",
    "roosevelt-dimes": "Roosevelt",
    "twenty-cent-pieces": "20c Piece",
    "barber-quarters": "Barber Quarter",
    "draped-bust-quarters": "Draped Bust 25c",
    "capped-bust-quarters": "Bust Quarter",
    "seated-liberty-quarters": "Seated Quarter",
    "youth-sports-quarters": "Youth Sports 25c",
    "standing-liberty-quarters": "SLQ",
    "washington-quarters": "Washington",
    "atb-5oz-silver": "ATB 5 oz",
    "seated-liberty-half-dollars": "Seated Half",
    "barber-half-dollars": "Barber Half",
    "early-half-dollars": "Early Half",
    "capped-bust-half-dollars": "Bust Half",
    "paralympic-half-dollars": "Paralympic Half",
    "walking-liberty-half-dollars": "Walker",
    "franklin-half-dollars": "Franklin",
    "kennedy-half-dollars": "Kennedy",
    "seated-liberty-dollars": "Seated Dollar",
    "trade-dollars": "Trade",
    "early-dollars": "Early Dollar",
    "gobrecht-dollars": "Gobrecht",
    "susan-b-anthony-dollars": "SBA",
    "presidential-dollars": "Presidential",
    "innovation-dollars": "Innovation $1",
    "morgan-dollars": "Morgan",
    "peace-dollars": "Peace",
    "modern-morgan-dollars": "Morgan",
    "modern-peace-dollars": "Peace",
    "ike-dollars": "Ike",
    "sacagawea-dollars": "Sacagawea",
    "american-silver-eagles": "ASE",
    "gold-eagles-5": "1/10 oz Gold Eagle",
    "gold-eagles-10": "1/4 oz Gold Eagle",
    "gold-eagles-25": "1/2 oz Gold Eagle",
    "gold-eagles-50": "1 oz Gold Eagle",
    "gold-buffalos": "Gold Buffalo",
    "fractional-gold-buffalos": "Gold Buffalo",
    "platinum-eagles-10": "1/10 oz Plat Eagle",
    "platinum-eagles-25": "1/4 oz Plat Eagle",
    "platinum-eagles-50": "1/2 oz Plat Eagle",
    "platinum-eagles-100": "1 oz Plat Eagle",
    "palladium-eagles": "Palladium Eagle",
    "first-spouse-gold": "First Spouse",
    "classic-gold-commemoratives": "Gold Commem",
    "modern-commemorative-gold-5": "$5 Commem",
    "modern-commemorative-gold-10": "$10 Commem",
    "mint-special-issues": "Mint Special",
    "silver-ike-blue-packs": "Ike Blue Pack",
    "silver-ike-brown-packs": "Ike Brown Pack",
}

# Variety words that describe the strike or metal, not which coin it is.
_NOT_A_NAME = re.compile(r"^(\d{4}/\d{2,4}|clad|silver|gold|doubled die.*|ddo|ddr|[a-z]/[a-z]|type \d|.*privy)$", re.I)
_DENOMINATION = {"10c": "Dime", "25c": "Quarter", "50c": "Half", "$1": "Dollar"}


def _theme(variety: str | None) -> str | None:
    """The coin's own name from its variety: the first part that names it ("Delaware, Silver" -> "Delaware")."""
    for part in (variety or "").split(","):
        part = part.strip()
        if part and not _NOT_A_NAME.match(part):
            return part
    return None


def short_name(slug: str, type_name: str, year: int, variety: str | None) -> str:
    theme = _theme(variety)
    if slug == "washington-quarters" and year >= 1999 and theme:
        return f"{theme} Quarter"  # states, D.C. and territories, America the Beautiful, American Women
    if slug == "classic-commemoratives" and theme:
        low = theme.lower()
        if "isabella" in low:
            return "Isabella Comm. Quarter"
        if "lafayette" in low:
            return "Lafayette Comm. Dollar"
        return f"{theme} Comm. Half"
    if slug == "modern-commemorative-halves" and theme:
        return f"{theme} Comm. Half"
    if slug == "modern-commemorative-dollars" and theme:
        return f"{theme} Comm. Dollar"
    if slug == "america-250" and theme:
        m = re.match(r"^(10c|25c|50c|\$1)\s+(.*)$", theme)
        if m:
            return f"{m.group(2)} {_DENOMINATION[m.group(1)]}"
        return theme
    return SHORT.get(slug, type_name)

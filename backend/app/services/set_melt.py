"""Silver content (troy ounces) of U.S. Mint and proof sets, for melt value.

Greysheet's metal fields need its Advanced tier, so this is worked out from what each set contains:
90% silver dimes, quarters and halves before 1965; 40% silver halves 1965-1970; the 1976 40% silver 3-coin sets;
90% silver (1992-2018) and .999 silver (2019 on) coins in Silver Proof sets; a 1 oz Silver Eagle in the Limited
Edition and $1 sets that include one. Clad sets have none.
"""

from . import series_match

# Pure silver per coin, troy oz
DIME_90, QUARTER_90, HALF_90 = 0.07234, 0.18084, 0.36169
QUARTER_40, HALF_40, DOLLAR_40 = 0.07395, 0.14789, 0.31625
DIME_999, QUARTER_999, HALF_999 = 0.08149, 0.20373, 0.40743
DOLLAR_90 = 0.77344  # silver commemorative dollar (Prestige sets)
EAGLE = 1.0

# Mints that struck circulating half dollars in mint-set years (Walking Liberty 1947, Franklin 1948-1963,
# Kennedy 1964); dimes and quarters come from the date list.
HALF_MINTS = {
    1947: "PD", 1948: "PD", 1949: "PDS", 1950: "PD", 1951: "PDS", 1952: "PDS", 1953: "PDS", 1954: "PDS",
    1955: "P", 1956: "P", 1957: "PD", 1958: "PD", 1959: "PD", 1960: "PD", 1961: "PD", 1962: "PD", 1963: "PD",
    1964: "PD",
}


def _mints(slug: str, year: int) -> int:
    strikes = series_match._issues().get(slug, {}).get(year) or {}
    return len(strikes.get("MS", set()))


def _proof_set_90(year: int) -> float:
    """Silver Proof sets' dime, quarters and half: 90% silver to 2018, .999 from 2019."""
    quarters = 6 if year == 2009 else 5 if year >= 1999 else 1
    if year >= 2019:
        return DIME_999 + quarters * QUARTER_999 + HALF_999
    return DIME_90 + quarters * QUARTER_90 + HALF_90


def silver_oz(slug: str, year: int, variety: str | None) -> float | None:
    """Ounces of pure silver in the set, 0.0 for clad sets, None when it isn't known."""
    v = (variety or "").lower()
    if slug == "us-mint-sets":
        if "silver eagle" in v:
            return EAGLE
        if "40% silver" in v:
            return QUARTER_40 + HALF_40 + DOLLAR_40
        if 1947 <= year <= 1964:
            copies = 2 if year <= 1958 else 1  # "double" sets until 1958
            dimes = _mints("roosevelt-dimes", year)
            quarters = _mints("washington-quarters", year)
            halves = len(HALF_MINTS.get(year, ""))
            return round(copies * (dimes * DIME_90 + quarters * QUARTER_90 + halves * HALF_90), 4)
        if 1965 <= year <= 1970:
            return HALF_40  # Special Mint Sets 1965-67; one 40% half in the 1968-70 sets
        return 0.0
    if slug == "us-proof-sets":
        if "prestige" in v:
            return DOLLAR_90 + (HALF_90 if year == 1993 else 0)  # the 1993 Madison half is silver too
        if year <= 1964:
            return DIME_90 + QUARTER_90 + HALF_90
        if 1968 <= year <= 1970:
            return HALF_40
        return 0.0
    if slug == "us-silver-proof-sets":
        if year == 1976:
            return QUARTER_40 + HALF_40 + DOLLAR_40
        if "premier" in v:
            return DIME_90 + QUARTER_90 + HALF_90
        if "quarters" in v:
            return 5 * (QUARTER_999 if year >= 2019 else QUARTER_90)
        if "innovation" in v:
            return None  # American Innovation dollars: not silver unless stated
        base = _proof_set_90(year)
        if "limited edition" in v:
            return round(base + EAGLE, 4)
        return round(base, 4)
    return None


def melt(slug: str, year: int, variety: str | None) -> dict | None:
    """{'oz', 'spot', 'value', 'as_of'} for a set with silver; {'oz': 0} for clad; None if unknown."""
    from . import metals

    oz = silver_oz(slug, year, variety)
    if oz is None:
        return None
    if oz == 0:
        return {"oz": 0.0, "spot": None, "value": 0.0, "as_of": None}
    price, updated = metals.spot("silver")
    if price is None:
        return {"oz": round(oz, 4), "spot": None, "value": None, "as_of": None}
    return {"oz": round(oz, 4), "spot": round(price, 2), "value": round(oz * price, 2), "as_of": updated}


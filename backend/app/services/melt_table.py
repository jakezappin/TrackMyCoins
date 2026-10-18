"""Metal content of U.S. coins, for the Precious Metals page's melt table and the metal in a user's collections.

Pure metal per coin, in troy ounces (copper in pounds, the way copper is priced). Weights and finenesses are the
Mint's standards: a 90% silver dime is 2.50 g, a Morgan dollar 26.73 g, a $20 Double Eagle 33.436 g of .900 gold.
Each entry also says which of the app's series and dates it covers, so a user's coins can be counted.
"""

from dataclasses import dataclass, field

TROY_OZ_G = 31.1034768
LB_G = 453.59237


def _oz(grams: float, fine: float) -> float:
    return round(grams * fine / TROY_OZ_G, 5)


def _lb(grams: float, fine: float) -> float:
    return round(grams * fine / LB_G, 6)


@dataclass(frozen=True)
class Rule:
    """Which coins of a series an entry covers."""

    slug: str
    first: int = 0
    last: int = 9999
    finishes: tuple[str, ...] = ()  # empty: any
    mints: tuple[str, ...] = ()  # empty: any


@dataclass(frozen=True)
class Entry:
    key: str
    group: str
    name: str
    years: str
    face: float  # dollars
    metal: str  # silver | gold | platinum | palladium | copper
    amount: float  # troy oz of pure metal (pounds for copper)
    composition: str
    rules: tuple[Rule, ...] = field(default_factory=tuple)


S90 = "90% silver"
G90 = "90% gold"
ENTRIES: list[Entry] = [
    # ---- 90% silver ----
    Entry("dime-90", "90% Silver", "Dime (Barber, Mercury, Roosevelt)", "1892–1964", 0.10, "silver", _oz(2.50, 0.9), S90,
          (Rule("seated-liberty-dimes", 1873), Rule("barber-dimes"), Rule("mercury-dimes", 0, 1945),
           Rule("roosevelt-dimes", 0, 1964), Rule("roosevelt-dimes", 1992, 2018, ("SPR",)))),
    Entry("quarter-90", "90% Silver", "Quarter (Barber, Standing Liberty, Washington)", "1892–1964", 0.25, "silver",
          _oz(6.25, 0.9), S90,
          (Rule("barber-quarters"), Rule("standing-liberty-quarters"), Rule("washington-quarters", 0, 1964),
           Rule("washington-quarters", 1992, 2018, ("SPR",)))),
    Entry("half-90", "90% Silver", "Half Dollar (Barber, Walking Liberty, Franklin, 1964 Kennedy)", "1892–1964", 0.50,
          "silver", _oz(12.50, 0.9), S90,
          (Rule("seated-liberty-half-dollars", 1873), Rule("barber-half-dollars"), Rule("kennedy-half-dollars", 1964, 1964),
           Rule("kennedy-half-dollars", 1992, 2018, ("SPR",)), Rule("classic-commemoratives"))),
    Entry("dollar-90", "90% Silver", "Morgan & Peace Dollar", "1878–1935", 1.00, "silver", _oz(26.73, 0.9), S90,
          (Rule("morgan-dollars"), Rule("peace-dollars"), Rule("seated-liberty-dollars"),
           Rule("modern-commemorative-dollars", 0, 2018))),
    Entry("trade-dollar", "90% Silver", "Trade Dollar", "1873–1885", 1.00, "silver", _oz(27.22, 0.9), S90,
          (Rule("trade-dollars"),)),
    Entry("half-dime", "90% Silver", "Seated Liberty Half Dime", "1853–1873", 0.05, "silver", _oz(1.24, 0.9), S90,
          (Rule("seated-liberty-half-dimes", 1853),)),
    Entry("three-cent-silver", "90% Silver", "Three-Cent Silver", "1854–1873", 0.03, "silver", _oz(0.75, 0.9), S90,
          (Rule("three-cent-silver", 1854),)),
    # ---- Lower silver ----
    Entry("war-nickel", "40% & 35% Silver", "Jefferson \"War\" Nickel", "1942–1945", 0.05, "silver", _oz(5.00, 0.35),
          "35% silver", (Rule("jefferson-nickels", 1943, 1945), Rule("jefferson-nickels", 1942, 1942, mints=("S",)))),
    Entry("kennedy-40", "40% & 35% Silver", "Kennedy Half Dollar", "1965–1970", 0.50, "silver", _oz(11.50, 0.4),
          "40% silver", (Rule("kennedy-half-dollars", 1965, 1970),)),
    Entry("ike-40", "40% & 35% Silver", "Eisenhower Dollar (S, silver)", "1971–1976", 1.00, "silver", _oz(24.59, 0.4),
          "40% silver", (Rule("ike-dollars", 1971, 1976, ("SPR",)), Rule("ike-dollars", 1971, 1976, ("MS",), ("S",)))),
    # ---- .999 silver ----
    Entry("silver-proof-dime", ".999 Silver", "Silver Proof Dime", "2019–", 0.10, "silver", _oz(2.537, 0.999), ".999 silver",
          (Rule("roosevelt-dimes", 2019, 9999, ("SPR",)),)),
    Entry("silver-proof-quarter", ".999 Silver", "Silver Proof Quarter", "2019–", 0.25, "silver", _oz(6.343, 0.999),
          ".999 silver", (Rule("washington-quarters", 2019, 9999, ("SPR",)),)),
    Entry("silver-proof-half", ".999 Silver", "Silver Proof Kennedy Half", "2019–", 0.50, "silver", _oz(12.685, 0.999),
          ".999 silver", (Rule("kennedy-half-dollars", 2019, 9999, ("SPR",)),)),
    Entry("modern-dollar", ".999 Silver", "Morgan & Peace Dollar (modern)", "2021–", 1.00, "silver", _oz(26.73, 0.999),
          ".999 silver", (Rule("modern-morgan-dollars"), Rule("modern-peace-dollars"),
                          Rule("modern-commemorative-dollars", 2019))),
    Entry("ase", ".999 Silver", "American Silver Eagle", "1986–", 1.00, "silver", 1.0, ".999 silver, 1 oz",
          (Rule("american-silver-eagles"),)),
    Entry("atb-5oz", ".999 Silver", "America the Beautiful 5 oz", "2010–2021", 0.25, "silver", 5.0, ".999 silver, 5 oz",
          (Rule("atb-5oz-silver"),)),
    # ---- Gold ----
    Entry("gold-1", "Gold", "$1 Gold Dollar", "1849–1889", 1.00, "gold", _oz(1.672, 0.9), G90, (Rule("gold-dollars"),)),
    Entry("gold-250", "Gold", "$2.50 Quarter Eagle", "1834–1929", 2.50, "gold", _oz(4.18, 0.9), G90,
          (Rule("classic-head-quarter-eagles"), Rule("liberty-quarter-eagles"), Rule("indian-quarter-eagles"))),
    Entry("gold-3", "Gold", "$3 Gold Piece", "1854–1889", 3.00, "gold", _oz(5.015, 0.9), G90, (Rule("three-dollar-gold"),)),
    Entry("gold-5", "Gold", "$5 Half Eagle", "1834–1929", 5.00, "gold", _oz(8.359, 0.9), G90,
          (Rule("classic-head-half-eagles"), Rule("liberty-half-eagles"), Rule("indian-half-eagles"))),
    Entry("gold-10", "Gold", "$10 Eagle", "1838–1933", 10.00, "gold", _oz(16.718, 0.9), G90,
          (Rule("liberty-eagles"), Rule("indian-eagles"))),
    Entry("gold-20", "Gold", "$20 Double Eagle", "1850–1933", 20.00, "gold", _oz(33.436, 0.9), G90,
          (Rule("liberty-double-eagles"), Rule("saint-gaudens-double-eagles"))),
    Entry("early-250", "Gold", "$2.50 Quarter Eagle (early, .9167)", "1796–1834", 2.50, "gold", _oz(4.37, 0.9167),
          "91.67% gold", (Rule("early-quarter-eagles"),)),
    Entry("early-5", "Gold", "$5 Half Eagle (early, .9167)", "1795–1834", 5.00, "gold", _oz(8.75, 0.9167), "91.67% gold",
          (Rule("early-half-eagles"),)),
    Entry("early-10", "Gold", "$10 Eagle (early, .9167)", "1795–1804", 10.00, "gold", _oz(17.5, 0.9167), "91.67% gold",
          (Rule("early-eagles"),)),
    Entry("age-tenth", "Gold", "American Gold Eagle 1/10 oz", "1986–", 5.00, "gold", 0.1, "22k gold", (Rule("gold-eagles-5"),)),
    Entry("age-quarter", "Gold", "American Gold Eagle 1/4 oz", "1986–", 10.00, "gold", 0.25, "22k gold", (Rule("gold-eagles-10"),)),
    Entry("age-half", "Gold", "American Gold Eagle 1/2 oz", "1986–", 25.00, "gold", 0.5, "22k gold", (Rule("gold-eagles-25"),)),
    Entry("age-1", "Gold", "American Gold Eagle 1 oz", "1986–", 50.00, "gold", 1.0, "22k gold", (Rule("gold-eagles-50"),)),
    Entry("buffalo", "Gold", "American Gold Buffalo 1 oz", "2006–", 50.00, "gold", 1.0, ".9999 gold", (Rule("gold-buffalos"),)),
    # ---- Platinum & palladium ----
    Entry("ape", "Platinum & Palladium", "American Platinum Eagle 1 oz", "1997–", 100.00, "platinum", 1.0, ".9995 platinum"),
    Entry("apde", "Platinum & Palladium", "American Palladium Eagle 1 oz", "2017–", 25.00, "palladium", 1.0, ".9995 palladium"),
    # ---- Copper ----
    Entry("cent-95", "Copper", "Lincoln & Indian Head Cent (bronze)", "1864–1982", 0.01, "copper", _lb(3.11, 0.95),
          "95% copper", (Rule("lincoln-cents", 1909, 1942), Rule("lincoln-cents", 1944, 1981), Rule("indian-head-cents", 1864))),
    Entry("large-cent", "Copper", "Large Cent", "1795–1857", 0.01, "copper", _lb(10.89, 1.0), "Copper",
          (Rule("large-cents", 1795),)),
    Entry("half-cent", "Copper", "Half Cent", "1795–1857", 0.005, "copper", _lb(5.44, 1.0), "Copper",
          (Rule("half-cents", 1795),)),
]
BY_KEY = {e.key: e for e in ENTRIES}

# Junk silver is traded by face value: $1 face of 90% dimes, quarters or halves holds 0.7234 oz of silver
# (less a little for wear; dealers often use 0.715).
JUNK_OZ_PER_DOLLAR = round(_oz(2.50, 0.9) * 10, 5)


def entry_for(slug: str, year: int, finish: str = "MS", mint: str = "P") -> Entry | None:
    """The metal-content entry for a coin of the app's series, or None (clad, base metal or unknown)."""
    for e in ENTRIES:
        for r in e.rules:
            if (r.slug == slug and r.first <= year <= r.last and (not r.finishes or finish in r.finishes)
                    and (not r.mints or mint in r.mints)):
                return e
    return None

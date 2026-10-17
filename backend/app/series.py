"""The coin series the app supports, and the collection types (series x finish) built from them.

Greysheet node ids come from its U.S. Coins catalog (see scripts/greysheet_check.py). Each finish lists
the catalog sections to pull; Silver Proof reuses the Proof sections and prefers the silver issues.
"""

from dataclasses import dataclass, field

# finish code -> (URL slug suffix, label, catalog strike)
FINISHES: dict[str, tuple[str, str, str]] = {
    "MS": ("", "MS", "MS"),
    "PR": ("-proof", "Proof", "PR"),
    "SPR": ("-silver-proof", "Silver Proof", "PR"),
}

CATEGORIES = [
    "Half Cents & Cents",
    "Nickels & Three Cents",
    "Half Dimes & Dimes",
    "Quarters",
    "Half Dollars",
    "Dollars",
    "Gold",
    "American Eagles",
    "Commemoratives",
]


@dataclass(frozen=True)
class Series:
    slug: str
    name: str  # singular, e.g. "Morgan Dollar"
    plural: str
    prefix: str  # inventory number prefix
    category: str
    mint_marks: tuple[str, ...]
    ms_nodes: tuple[int, ...]
    pr_nodes: tuple[int, ...] = ()
    silver_proofs: bool = False  # has silver proofs issued alongside clad ones
    finishes: tuple[str, ...] = field(init=False)

    def __post_init__(self):
        f = ["MS"] + (["PR"] if self.pr_nodes else []) + (["SPR"] if self.silver_proofs else [])
        object.__setattr__(self, "finishes", tuple(f))

    @property
    def metal(self) -> str:
        """For the placeholder artwork: gold for gold series, silver otherwise."""
        return "gold" if self.category == "Gold" or self.slug.startswith("gold-eagles") else "silver"

    def nodes_for(self, finish: str) -> tuple[int, ...]:
        return self.ms_nodes if finish == "MS" else self.pr_nodes


C, N, D, Q, H, DOL, GOLD, ASE, COM = CATEGORIES
GOLD_MINTS = ("P", "C", "D", "O", "S", "CC")  # C = Charlotte, D = Dahlonega (to 1861) or Denver
SERIES: list[Series] = [
    # Cents
    Series("half-cents", "Half Cent", "Half Cents", "HFC", C, ("P",),
           (8908, 9672, 9673, 9674), (14965, 9529)),
    Series("large-cents", "Large Cent", "Large Cents", "LGC", C, ("P",),
           (8909, 9675, 9676, 9677, 9678), (14966, 9530)),
    Series("flying-eagle-cents", "Flying Eagle Cent", "Flying Eagle Cents", "FEC", C, ("P",), (9030,), (9531,)),
    Series("indian-head-cents", "Indian Head Cent", "Indian Head Cents", "IHC", C, ("P", "S"), (8910,), (8911,)),
    Series("lincoln-cents", "Lincoln Cent", "Lincoln Cents", "LIN", C, ("P", "D", "S", "W"),
           (8912, 9645, 9687), (8913, 9646, 9688)),
    # Nickels & three cents
    Series("three-cent-silver", "Trime", "Trimes", "TCS", N, ("P", "O"), (8927,), (8928,)),
    Series("three-cent-nickels", "Three Cent Nickel", "Three Cent Nickels", "TCN", N, ("P",), (8916,), (8917,)),
    Series("shield-nickels", "Shield Nickel", "Shield Nickels", "SHN", N, ("P",), (8918,), (8919,)),
    Series("liberty-head-nickels", "Liberty Head (V) Nickel", "Liberty Head (V) Nickels", "LHN", N,
           ("P", "D", "S"), (8920,), (8921,)),
    Series("buffalo-nickels", "Buffalo Nickel", "Buffalo Nickels", "BUF", N, ("P", "D", "S"), (8922,), (8923,)),
    Series("jefferson-nickels", "Jefferson Nickel", "Jefferson Nickels", "JEF", N, ("P", "D", "S"), (8925,), (8926,)),
    # Half dimes & dimes
    Series("seated-liberty-half-dimes", "Seated Liberty Half Dime", "Seated Liberty Half Dimes", "SLHD", D,
           ("P", "O", "S"), (8930,), (8931,)),
    Series("seated-liberty-dimes", "Seated Liberty Dime", "Seated Liberty Dimes", "SLDM", D,
           ("P", "O", "S", "CC"), (8933,), (8934,)),
    Series("barber-dimes", "Barber Dime", "Barber Dimes", "BRD", D, ("P", "O", "S", "D"), (8935,), (8936,)),
    Series("mercury-dimes", "Mercury Dime", "Mercury Dimes", "MER", D, ("P", "D", "S"), (8937,), (8938,)),
    Series("roosevelt-dimes", "Roosevelt Dime", "Roosevelt Dimes", "ROS", D, ("P", "D", "S", "W"),
           (8939,), (8940,), silver_proofs=True),
    # Quarters
    Series("barber-quarters", "Barber Quarter", "Barber Quarters", "BRQ", Q, ("P", "O", "S", "D"), (8946,), (8947,)),
    Series("standing-liberty-quarters", "Standing Liberty Quarter", "Standing Liberty Quarters", "SLQ", Q,
           ("P", "D", "S"), (8948,)),
    # Includes 50 States, D.C. & Territories, America the Beautiful, Crossing the Delaware, American Women.
    Series("washington-quarters", "Washington Quarter", "Washington Quarters", "WAS", Q, ("P", "D", "S", "W"),
           (8949, 8950, 9689, 9567, 12168, 12169), (8951, 8952, 9690, 9301, 15354, 12170), silver_proofs=True),
    # Half dollars
    Series("seated-liberty-half-dollars", "Seated Liberty Half Dollar", "Seated Liberty Half Dollars", "SLH", H,
           ("P", "O", "S", "CC"), (8955,), (8956,)),
    Series("barber-half-dollars", "Barber Half Dollar", "Barber Half Dollars", "BRH", H,
           ("P", "O", "S", "D"), (8957,), (8958,)),
    Series("kennedy-half-dollars", "Kennedy Half Dollar", "Kennedy Half Dollars", "KEN", H, ("P", "D", "S", "W"),
           (8963,), (8964,), silver_proofs=True),
    # Dollars
    Series("seated-liberty-dollars", "Seated Liberty Dollar", "Seated Liberty Dollars", "SLD", DOL,
           ("P", "O", "S", "CC"), (8967,), (8968,)),
    Series("trade-dollars", "Trade Dollar", "Trade Dollars", "TRD", DOL, ("P", "S", "CC"), (8969,), (8970,)),
    Series("morgan-dollars", "Morgan Dollar", "Morgan Dollars", "MOR", DOL, ("P", "CC", "O", "S", "D"),
           (8971,), (8972,)),
    Series("peace-dollars", "Peace Dollar", "Peace Dollars", "PEA", DOL, ("P", "D", "S"), (8973,)),
    Series("ike-dollars", "Ike Dollar", "Ike Dollars", "IKE", DOL, ("P", "D", "S"), (8974,), (8975,),
           silver_proofs=True),
    # Includes Native American dollars (2009-), which share the Sacagawea obverse.
    Series("sacagawea-dollars", "Sacagawea Dollar", "Sacagawea Dollars", "SAC", DOL, ("P", "D", "S", "W"),
           (9299, 15901), (9556, 15902)),
    # Classic U.S. gold. Name and plural match because collectors say "$20 Saint-Gaudens" for both.
    Series("gold-dollars", "$1 Gold", "$1 Gold", "G1", GOLD, GOLD_MINTS, (8978, 10336, 10335), (8979,)),
    Series("liberty-quarter-eagles", "$2.50 Liberty", "$2.50 Liberty", "G2L", GOLD, GOLD_MINTS, (8981,), (8982,)),
    Series("indian-quarter-eagles", "$2.50 Indian", "$2.50 Indian", "G2I", GOLD, ("P", "D"), (8983,), (8984,)),
    Series("three-dollar-gold", "$3 Princess", "$3 Princess", "G3", GOLD, GOLD_MINTS, (8985,), (8986,)),
    Series("liberty-half-eagles", "$5 Liberty", "$5 Liberty", "G5L", GOLD, GOLD_MINTS, (10337, 8989), (8990,)),
    Series("indian-half-eagles", "$5 Indian", "$5 Indian", "G5I", GOLD, ("P", "D", "O", "S"), (8991,), (8992,)),
    Series("liberty-eagles", "$10 Liberty", "$10 Liberty", "G10L", GOLD, GOLD_MINTS, (10338, 8994), (8995,)),
    Series("indian-eagles", "$10 Indian", "$10 Indian", "G10I", GOLD, ("P", "D", "S"), (8996,), (8997,)),
    Series("liberty-double-eagles", "$20 Liberty", "$20 Liberty", "G20L", GOLD, GOLD_MINTS,
           (10339, 10340, 8998), (8999,)),
    Series("saint-gaudens-double-eagles", "$20 Saint-Gaudens", "$20 Saint-Gaudens", "G20S", GOLD, ("P", "D", "S"),
           (9000,), (9001,)),
    # American Silver Eagles (1986-): bullion and burnished uncirculated (MS), and proofs.
    Series("american-silver-eagles", "American Silver Eagle", "American Silver Eagles", "ASE", ASE,
           ("P", "S", "W"), (9011,), (9540,)),
    # American Gold Eagles (1986-), one series per size since each is collected as its own date set.
    Series("gold-eagles-5", "$5 Gold Eagle (1/10 oz)", "$5 Gold Eagles (1/10 oz)", "AGE5", ASE, ("P", "W"),
           (9012,), (9541,)),
    Series("gold-eagles-10", "$10 Gold Eagle (1/4 oz)", "$10 Gold Eagles (1/4 oz)", "AGE10", ASE, ("P", "W"),
           (9013,), (9542,)),
    Series("gold-eagles-25", "$25 Gold Eagle (1/2 oz)", "$25 Gold Eagles (1/2 oz)", "AGE25", ASE, ("P", "W"),
           (9014,), (9543,)),
    Series("gold-eagles-50", "$50 Gold Eagle (1 oz)", "$50 Gold Eagles (1 oz)", "AGE50", ASE, ("P", "W"),
           (9015,), (9544,)),
    # Classic silver commemoratives 1892-1954: half dollars plus the Isabella quarter and Lafayette dollar.
    Series("classic-commemoratives", "Classic Commemorative", "Classic Commemoratives", "COM", COM,
           ("P", "D", "S"), (9003,)),
]

BY_SLUG = {s.slug: s for s in SERIES}


def collection_type_slug(series_slug: str, finish: str) -> str:
    return series_slug + FINISHES[finish][0]


def parse_collection_type_slug(slug: str) -> tuple[Series, str] | None:
    """'kennedy-half-dollars-silver-proof' -> (Kennedy series, 'SPR')."""
    for finish in ("SPR", "PR", "MS"):  # longest suffix first
        suffix = FINISHES[finish][0]
        if suffix and not slug.endswith(suffix):
            continue
        base = slug[: len(slug) - len(suffix)] if suffix else slug
        s = BY_SLUG.get(base)
        if s and finish in s.finishes:
            return s, finish
    return None


def collection_type_label(series: Series, finish: str) -> str:
    """'Peace Dollars' for MS-only series, otherwise 'Kennedy Half Dollars – Proof'."""
    if series.finishes == ("MS",):
        return series.plural
    return f"{series.plural} – {FINISHES[finish][1]}"

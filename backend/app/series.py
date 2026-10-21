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
    "Mint & Proof Sets",
    "Type Sets",
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
    # Type sets only: one checklist line per design, as (label, Greysheet node). The coins themselves belong
    # to the series that own those nodes, chosen when each coin is added.
    type_rows: tuple[tuple[str, int], ...] = ()
    # Catalog sections shared with another series (modern Morgan & Peace): keep entries whose name matches
    # `only` and not `skip` (regexes).
    only: str | None = None
    skip: str | None = None
    # "set": U.S. Mint packaged sets (mint sets, proof sets) — kept in the Mint's packaging, not graded, priced
    # at Greysheet's single "OGP" grade, one checklist line per year.
    kind: str = "coin"
    finishes: tuple[str, ...] = field(init=False)

    def __post_init__(self):
        f = (["MS"] if self.ms_nodes or self.type_rows else []) + (["PR"] if self.pr_nodes else [])
        f += ["SPR"] if self.silver_proofs else []
        object.__setattr__(self, "finishes", tuple(f))

    @property
    def is_set(self) -> bool:
        return self.kind == "set"

    @property
    def is_type_set(self) -> bool:
        return bool(self.type_rows)

    @property
    def metal(self) -> str:
        """For the placeholder artwork: gold for gold series, silver otherwise."""
        gold = self.category == "Gold" or self.slug.startswith(("gold-eagles", "gold-buffalo", "gold-type"))
        return "gold" if gold else "silver"


C, N, D, Q, H, DOL, GOLD, ASE, COM, SETS, TYPESETS = CATEGORIES
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
           (8912, 9645, 9687, 9695), (8913, 9646, 9688)),  # + Special Mint Set coins (1964-67)
    Series("two-cent-pieces", "Two Cent Piece", "Two Cent Pieces", "TWC", C, ("P",), (8914,), (8915,)),
    # Nickels & three cents
    Series("three-cent-silver", "Three Cent Silver", "Three Cent Silver (Trimes)", "TCS", N, ("P", "O"), (8927,), (8928,)),
    Series("three-cent-nickels", "Three Cent Nickel", "Three Cent Nickels", "TCN", N, ("P",), (8916,), (8917,)),
    Series("shield-nickels", "Shield Nickel", "Shield Nickels", "SHN", N, ("P",), (8918,), (8919,)),
    Series("liberty-head-nickels", "Liberty Head (V) Nickel", "Liberty Head (V) Nickels", "LHN", N,
           ("P", "D", "S"), (8920,), (8921,)),
    Series("buffalo-nickels", "Buffalo Nickel", "Buffalo Nickels", "BUF", N, ("P", "D", "S"), (8922,), (8923,)),
    Series("jefferson-nickels", "Jefferson Nickel", "Jefferson Nickels", "JEF", N, ("P", "D", "S", "W"), (8925, 9692), (8926,)),
    # Half dimes & dimes
    # The 1792 half disme, Flowing Hair (1794-95) and Draped Bust (1796-1805) half dimes.
    Series("early-half-dimes", "Flowing Hair & Draped Bust Half Dime", "Flowing Hair & Draped Bust Half Dimes", "EHD",
           D, ("P",), (9663, 9664, 9665)),
    Series("capped-bust-half-dimes", "Capped Bust Half Dime", "Capped Bust Half Dimes", "CBHD", D, ("P",),
           (8929,), (9335,)),
    Series("seated-liberty-half-dimes", "Seated Liberty Half Dime", "Seated Liberty Half Dimes", "SLHD", D,
           ("P", "O", "S"), (8930,), (8931,)),
    Series("draped-bust-dimes", "Draped Bust Dime", "Draped Bust Dimes", "DBD", D, ("P",), (9662,)),
    Series("capped-bust-dimes", "Capped Bust Dime", "Capped Bust Dimes", "CBD", D, ("P",), (8932,), (9532,)),
    Series("seated-liberty-dimes", "Seated Liberty Dime", "Seated Liberty Dimes", "SLDM", D,
           ("P", "O", "S", "CC"), (8933,), (8934,)),
    Series("barber-dimes", "Barber Dime", "Barber Dimes", "BRD", D, ("P", "O", "S", "D"), (8935,), (8936,)),
    Series("mercury-dimes", "Mercury Dime", "Mercury Dimes", "MER", D, ("P", "D", "S"), (8937,), (8938,)),
    Series("roosevelt-dimes", "Roosevelt Dime", "Roosevelt Dimes", "ROS", D, ("P", "D", "S", "W"),
           (8939, 9691), (8940,), silver_proofs=True),
    # Quarters (and the short-lived twenty cent piece)
    Series("twenty-cent-pieces", "Twenty Cent Piece", "Twenty Cent Pieces", "TWN", Q, ("P", "S", "CC"), (8941,), (8942,)),
    Series("draped-bust-quarters", "Draped Bust Quarter", "Draped Bust Quarters", "DBQ", Q, ("P",), (8943,)),
    Series("capped-bust-quarters", "Capped Bust Quarter", "Capped Bust Quarters", "CBQ", Q, ("P",), (9649,), (9317,)),
    Series("seated-liberty-quarters", "Seated Liberty Quarter", "Seated Liberty Quarters", "STQ", Q,
           ("P", "O", "S", "CC"), (8944,), (8945,)),
    Series("barber-quarters", "Barber Quarter", "Barber Quarters", "BRQ", Q, ("P", "O", "S", "D"), (8946,), (8947,)),
    Series("standing-liberty-quarters", "Standing Liberty Quarter", "Standing Liberty Quarters", "SLQ", Q,
           ("P", "D", "S"), (8948,)),
    # Includes 50 States, D.C. & Territories, America the Beautiful, Crossing the Delaware, American Women.
    Series("washington-quarters", "Washington Quarter", "Washington Quarters", "WAS", Q, ("P", "D", "S", "W"),
           (8949, 8950, 9689, 9567, 12168, 12169, 9696), (8951, 8952, 9690, 9301, 15354, 12170), silver_proofs=True),
    # Youth Sports quarters (2027-2030), one design per sport.
    Series("youth-sports-quarters", "Youth Sports Quarter", "Youth Sports Quarters", "YSQ", Q, ("P", "D", "S", "W"),
           (16289,), (16290,)),
    # 5 oz silver bullion quarters, 2010-2021: one per design, plus the collector "P" Satin Finish versions.
    Series("atb-5oz-silver", "America the Beautiful 5 oz Silver", "America the Beautiful 5 oz Silver", "ATB5", Q,
           ("P",), (9598,)),
    # Half dollars
    Series("early-half-dollars", "Flowing Hair & Draped Bust Half Dollar", "Flowing Hair & Draped Bust Half Dollars",
           "EHH", H, ("P",), (9659, 9660)),
    Series("capped-bust-half-dollars", "Capped Bust Half Dollar", "Capped Bust Half Dollars", "CBH", H, ("P", "O"),
           (8954,), (9533,)),
    Series("seated-liberty-half-dollars", "Seated Liberty Half Dollar", "Seated Liberty Half Dollars", "SLH", H,
           ("P", "O", "S", "CC"), (8955,), (8956,)),
    Series("barber-half-dollars", "Barber Half Dollar", "Barber Half Dollars", "BRH", H,
           ("P", "O", "S", "D"), (8957,), (8958,)),
    Series("walking-liberty-half-dollars", "Walking Liberty Half Dollar", "Walking Liberty Half Dollars", "WLH", H,
           ("P", "D", "S"), (8959,), (8960,)),
    Series("franklin-half-dollars", "Franklin Half Dollar", "Franklin Half Dollars", "FRH", H, ("P", "D", "S"),
           (8961,), (8962,)),
    Series("kennedy-half-dollars", "Kennedy Half Dollar", "Kennedy Half Dollars", "KEN", H, ("P", "D", "S", "W"),
           (8963, 9693), (8964,), silver_proofs=True),
    # Paralympic Sports half dollars (2027-2030).
    Series("paralympic-half-dollars", "Paralympic Sports Half Dollar", "Paralympic Sports Half Dollars", "PSH", H,
           ("P", "D", "S", "W"), (16291,), (16292,)),
    # Dollars
    Series("early-dollars", "Flowing Hair & Draped Bust Dollar", "Flowing Hair & Draped Bust Dollars", "EDL", DOL,
           ("P",), (9661, 8965), (9534,)),
    # Struck only as proofs (originals and restrikes), so its only collection type is Proof.
    Series("gobrecht-dollars", "Gobrecht Dollar", "Gobrecht Dollars", "GOB", DOL, ("P",), (), (8966,)),
    Series("seated-liberty-dollars", "Seated Liberty Dollar", "Seated Liberty Dollars", "SLD", DOL,
           ("P", "O", "S", "CC"), (8967,), (8968,)),
    Series("trade-dollars", "Trade Dollar", "Trade Dollars", "TRD", DOL, ("P", "S", "CC"), (8969,), (8970,)),
    Series("morgan-dollars", "Morgan Dollar", "Morgan Dollars", "MOR", DOL, ("P", "CC", "O", "S", "D"),
           (8971,), (8972,)),
    Series("peace-dollars", "Peace Dollar", "Peace Dollars", "PEA", DOL, ("P", "D", "S"), (8973,), (9560,)),
    # The U.S. Mint's Morgan and Peace dollars from 2021 on (Greysheet lists both in one section; two-coin
    # sets are left out). Enhanced Uncirculated, privies and Reverse Proofs are lines of their own.
    Series("modern-morgan-dollars", "Modern Morgan Dollar", "Modern Morgan Dollars", "MMD", DOL,
           ("P", "D", "S", "W"), (10536,), (15351,), only=r"\bMorgan\b", skip=r"\bPeace\b|\bSet\b"),
    Series("modern-peace-dollars", "Modern Peace Dollar", "Modern Peace Dollars", "MPD", DOL,
           ("P", "D", "S", "W"), (10536,), (15351,), only=r"\bPeace\b", skip=r"\bMorgan\b|\bSet\b"),
    Series("ike-dollars", "Ike Dollar", "Ike Dollars", "IKE", DOL, ("P", "D", "S"), (8974,), (8975,),
           silver_proofs=True),
    Series("susan-b-anthony-dollars", "Susan B. Anthony Dollar", "Susan B. Anthony Dollars", "SBA", DOL,
           ("P", "D", "S"), (8976,), (9566,)),
    Series("presidential-dollars", "Presidential Dollar", "Presidential Dollars", "PRES", DOL, ("P", "D", "S"),
           (8977,), (9555,)),
    Series("innovation-dollars", "American Innovation Dollar", "American Innovation Dollars", "AID", DOL,
           ("P", "D", "S"), (9603,), (9700,)),
    # Includes Native American dollars (2009-), which share the Sacagawea obverse.
    Series("sacagawea-dollars", "Sacagawea Dollar", "Sacagawea Dollars", "SAC", DOL, ("P", "D", "S", "W"),
           (9299, 15901), (9556, 15902)),
    # Classic U.S. gold. Name and plural match because collectors say "$20 Saint-Gaudens" for both.
    # Early gold (pre-1840 designs)
    Series("early-quarter-eagles", "$2.50 Draped & Capped Bust", "$2.50 Draped & Capped Bust", "G2E", GOLD, ("P",),
           (9666, 9667), (9668,)),
    Series("classic-head-quarter-eagles", "$2.50 Classic Head", "$2.50 Classic Head", "G2C", GOLD, ("P", "C", "D", "O"),
           (8980,), (9611,)),
    Series("early-half-eagles", "$5 Draped & Capped Bust", "$5 Draped & Capped Bust", "G5E", GOLD, ("P",),
           (9669, 9670), (9671,)),
    Series("classic-head-half-eagles", "$5 Classic Head", "$5 Classic Head", "G5C", GOLD, ("P", "C", "D"),
           (8988,), (9610,)),
    Series("early-eagles", "$10 Draped Bust", "$10 Draped Bust", "G10E", GOLD, ("P",), (8993,), (9579,)),
    Series("gold-dollars", "$1 Gold", "$1 Gold", "G1", GOLD, GOLD_MINTS, (8978, 10336, 10335), (8979,)),
    Series("liberty-quarter-eagles", "$2.50 Liberty", "$2.50 Liberty", "G2L", GOLD, GOLD_MINTS, (8981,), (8982,)),
    # $4 Stella was only struck as proofs (1879-1880), so its only collection type is Proof.
    Series("four-dollar-stella", "$4 Stella", "$4 Stella", "G4", GOLD, ("P",), (), (8987,)),
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
    # American Gold Buffalo, 1 oz .9999 fine (2006-). The 2008-only fractional sizes aren't included.
    Series("gold-buffalos", "$50 Gold Buffalo", "$50 Gold Buffalos", "GB50", ASE, ("P", "W"), (9254,), (9545,)),
    # Fractional Gold Buffalos ($5, $10, $25: 2008, and again from 2026). Each section has uncirculated and proof.
    Series("fractional-gold-buffalos", "Fractional Gold Buffalo", "Fractional Gold Buffalos", "GBF", ASE,
           ("W",), (9255, 9256, 9257), (9255, 9256, 9257)),
    # American Platinum Eagles, one series per size; the $100 proof has a new design every year.
    Series("platinum-eagles-10", "$10 Platinum Eagle (1/10 oz)", "$10 Platinum Eagles (1/10 oz)", "APE10", ASE,
           ("P", "W"), (9016,), (9549,)),
    Series("platinum-eagles-25", "$25 Platinum Eagle (1/4 oz)", "$25 Platinum Eagles (1/4 oz)", "APE25", ASE,
           ("P", "W"), (9017,), (9548,)),
    Series("platinum-eagles-50", "$50 Platinum Eagle (1/2 oz)", "$50 Platinum Eagles (1/2 oz)", "APE50", ASE,
           ("P", "W"), (9018,), (9547,)),
    Series("platinum-eagles-100", "$100 Platinum Eagle (1 oz)", "$100 Platinum Eagles (1 oz)", "APE100", ASE,
           ("P", "W"), (9019,), (9546,)),
    Series("palladium-eagles", "$25 Palladium Eagle", "$25 Palladium Eagles", "APD25", ASE, ("P", "W"),
           (9568,), (15355,)),
    Series("first-spouse-gold", "$10 First Spouse Gold", "$10 First Spouse Gold", "FSG", ASE, ("W",),
           (9009,), (9552,)),
    # Classic silver commemoratives 1892-1954: half dollars plus the Isabella quarter and Lafayette dollar.
    Series("classic-commemoratives", "Classic Commemorative", "Classic Commemoratives", "COM", COM,
           ("P", "D", "S"), (9003,), (9578,)),
    Series("classic-gold-commemoratives", "Classic Gold Commemorative", "Classic Gold Commemoratives", "CGC", COM,
           ("P",), (9002,)),
    # Modern commemoratives (1982 on): clad half dollars (the 1982 Washington is silver) and silver dollars.
    Series("modern-commemorative-halves", "Modern Commemorative Half Dollar", "Modern Commemorative Half Dollars",
           "MCH", COM, ("P", "D", "S", "W"), (9005,), (9570,)),
    Series("modern-commemorative-dollars", "Modern Commemorative Dollar", "Modern Commemorative Dollars",
           "MCD", COM, ("P", "D", "S", "W"), (9006,), (9554,)),
    Series("modern-commemorative-gold-5", "$5 Modern Commemorative", "$5 Modern Commemoratives", "MC5", COM,
           ("P", "D", "S", "W"), (9007,), (9559,)),
    Series("modern-commemorative-gold-10", "$10 Modern Commemorative", "$10 Modern Commemoratives", "MC10", COM,
           ("P", "D", "S", "W"), (9008,), (9612,)),
    # The Mint's one-off and newer gold and silver issues: the 2009 Ultra High Relief, 2016 Centennial Gold,
    # American Liberty $100, Liberty & Britannia, the 230th Anniversary Flowing Hair, Comic Art, Best of the Mint
    # and the 2020 $25 commemorative.
    Series("mint-special-issues", "U.S. Mint Special Issue", "U.S. Mint Special Issues", "MSI", COM,
           ("P", "D", "S", "W"), (9022, 9563, 9608, 15186, 15839, 15029, 15897, 11830),
           (9022, 9563, 9608, 15186, 15839, 15029, 15897, 11830)),
    # The Semiquincentennial (dual-dated 1776~2026): the Emerging Liberty dime, five quarters, the Enduring Liberty
    # half and the dollar; proofs (clad and silver) and the Liberty Bell silver and gold issues.
    Series("america-250", "America 250 (2026)", "America 250 (2026)", "A250", COM, ("P", "D", "S", "W"),
           (16071, 16037, 16073, 16278), (16072, 16038, 16074, 16066), silver_proofs=True),
    # U.S. Mint packaged sets, one line per year (Greysheet's multi-year bundles are left out). Proof sets
    # are split into clad (and pre-1965 silver) Proof Sets and Silver Proof Sets (1976 3-coin, 1992 on).
    Series("us-mint-sets", "U.S. Mint Set", "U.S. Mint Sets", "UMS", SETS, ("P", "D", "S", "W"), (9551, 9694),
           skip=r"Items\)|Collection \d", kind="set"),
    Series("us-proof-sets", "U.S. Proof Set", "U.S. Proof Sets", "UPS", SETS, ("P", "S", "W"), (9020,),
           skip=r"\bSilver\b|Items\)|Collection \d", kind="set"),
    Series("us-silver-proof-sets", "U.S. Silver Proof Set", "U.S. Silver Proof Sets", "USPS", SETS,
           ("P", "S", "W"), (9020,), only=r"\bSilver\b", skip=r"Items\)|Collection \d", kind="set"),
    # 40% silver Ikes in their Mint packaging: uncirculated (blue) and proof (brown).
    Series("silver-ike-blue-packs", "Silver Ike, Blue Pack", "Silver Ikes, Blue Packs", "IKB", SETS, ("S",), (10341,),
           kind="set"),
    Series("silver-ike-brown-packs", "Silver Ike, Brown Pack", "Silver Ikes, Brown Packs", "IKBR", SETS, ("S",),
           (10342,), kind="set"),
    # Multi-coin American Eagle and Gold Buffalo sets, and modern commemorative sets.
    Series("bullion-eagle-sets", "American Eagle & Buffalo Set", "American Eagle & Buffalo Sets", "AES", SETS,
           ("P", "S", "W"), (9565, 9010, 9021, 9258), kind="set"),
    Series("modern-commemorative-sets", "Modern Commemorative Set", "Modern Commemorative Sets", "MCS", SETS,
           ("P", "D", "S", "W"), (9004,), kind="set"),
]

# Mixed-series type sets. Each line is one design; a coin fills it when its catalog entry comes from that node.
SERIES.append(
    Series("gold-type-set", "Gold Type Set", "Gold Type Sets", "GTS", TYPESETS, (), (), type_rows=(
        ("$1 Gold Type 1 (1849–1854)", 8978),
        ("$1 Gold Type 2 (1854–1856)", 10336),
        ("$1 Gold Type 3 (1856–1889)", 10335),
        ("$2.50 Draped Bust (1796–1807)", 9666),
        ("$2.50 Capped Bust (1808–1834)", 9667),
        ("$2.50 Classic Head (1834–1839)", 8980),
        ("$2.50 Liberty (1840–1907)", 8981),
        ("$2.50 Indian (1908–1929)", 8983),
        ("$3 Princess (1854–1889)", 8985),
        ("$5 Draped Bust (1795–1807)", 9669),
        ("$5 Capped Bust (1807–1834)", 9670),
        ("$5 Classic Head (1834–1838)", 8988),
        ("$5 Liberty, No Motto (1839–1866)", 10337),
        ("$5 Liberty, With Motto (1866–1908)", 8989),
        ("$5 Indian (1908–1929)", 8991),
        ("$10 Draped Bust (1795–1804)", 8993),
        ("$10 Liberty, No Motto (1838–1866)", 10338),
        ("$10 Liberty, With Motto (1866–1907)", 8994),
        ("$10 Indian (1907–1933)", 8996),
        ("$20 Liberty Type 1 (1849–1866)", 10339),
        ("$20 Liberty Type 2 (1866–1876)", 10340),
        ("$20 Liberty Type 3 (1877–1907)", 8998),
        ("$20 Saint-Gaudens (1907–1933)", 9000),
    ))
)

BY_SLUG = {s.slug: s for s in SERIES}
# Which series owns each Greysheet node (for type sets).
SERIES_BY_NODE = {n: s for s in SERIES for n in (*s.ms_nodes, *s.pr_nodes)}


def type_set_members(series: Series) -> list[Series]:
    """The series a type set's coins can come from, in checklist order."""
    seen: dict[str, Series] = {}
    for _, node in series.type_rows:
        member = SERIES_BY_NODE[node]
        seen.setdefault(member.slug, member)
    return list(seen.values())


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
    if series.is_type_set:
        return series.name  # "Gold Type Set"
    if len(series.finishes) == 1 and finish == "MS":
        return series.plural
    return f"{series.plural} – {FINISHES[finish][1]}"

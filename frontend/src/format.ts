import type { Coin, CoinFields, CoinType, Collection } from "./api";

// ---- URLs ----
export const collectionPath = (c: Pick<Collection, "collection_type_slug" | "number">) =>
  `/collections/${c.collection_type_slug}/${c.number}`;
export const soldPath = (typeSlug: string) => `/collections/${typeSlug}/sold`;
export const coinPath = (inv: string) => `/coins/${inv}`;

/** "gold" or "silver" for a coin's placeholder artwork. */
export const metalFor = (coinTypes: CoinType[], coinTypeId: number) =>
  coinTypes.find((t) => t.id === coinTypeId)?.metal ?? "silver";

const FINISH_ORDER = { MS: 0, PR: 1, SPR: 2 } as const;
export const FINISH_LABEL = { MS: "MS", PR: "Proof", SPR: "Silver Proof" } as const;

/** The user's collections grouped by series, in catalog order; series with no collections are left out. */
export function collectionsBySeries(coinTypes: CoinType[], collections: Collection[]) {
  return coinTypes
    .map((type) => ({
      type,
      collections: collections
        .filter((c) => c.coin_type_id === type.id)
        .sort((a, b) => FINISH_ORDER[a.finish] - FINISH_ORDER[b.finish] || a.number - b.number),
    }))
    .filter((g) => g.collections.length > 0);
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function money(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? usd.format(n) : "—";
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Plain dates (YYYY-MM-DD) are shown as-is in local time. Server times are UTC; one sent without a zone
  // ("2026-10-17T03:12:06") would otherwise be read as local time and show the next day in the evening.
  const zoned = /[zZ]|[+-]\d\d:?\d\d$/.test(iso);
  const d = iso.length === 10 ? new Date(iso + "T00:00:00") : new Date(zoned ? iso : iso.replace(" ", "T") + "Z");
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function dateMint(c: Pick<CoinFields, "year" | "mint_mark">): string {
  if (!c.year) return "—";
  return c.mint_mark && c.mint_mark !== "P" ? `${c.year}-${c.mint_mark}` : `${c.year}`;
}

/** "MS65+ DMPL", or for raw coins "Raw AU55", "Raw AU" or just "Raw". */
type GradeFields = Pick<CoinFields, "grading_service" | "grade_prefix" | "grade" | "grade_plus" | "grade_star" | "strike_designation"> &
  Partial<Pick<CoinFields, "details" | "details_problem">>;

/** Problems a Details grade can name (matches backend services/details.py). */
export const DETAILS_PROBLEMS: Record<string, string> = {
  cleaned: "Cleaned",
  "environmental-damage": "Environmental Damage",
  scratched: "Scratched",
  tooled: "Tooled",
  "altered-surfaces": "Altered Surfaces",
  damaged: "Damaged",
  holed: "Holed",
  repaired: "Repaired",
  graffiti: "Graffiti",
  bent: "Bent",
  "rim-damage": "Rim Damage",
  "questionable-color": "Questionable Color",
  polished: "Polished",
  whizzed: "Whizzed",
  other: "Other",
};
type ToningFields = Pick<CoinFields, "toning_obverse" | "toning_reverse" | "toning_dual" | "toning_rainbow">;
type SlabFields = Pick<
  CoinFields,
  | "slab_soapbox" | "slab_ngc_fatty" | "slab_rattler" | "slab_ogh" | "gsa_hard_pack" | "gsa_soft_pack" | "ike_blue_pack"
  | "ike_brown_pack" | "ogp" | "capital_holder"
>;

export function gradeLabel(c: GradeFields): string {
  if (c.details) {
    // "AU55 Details · Cleaned": no plus, star or designation on a Details grade.
    let d = `${c.grade_prefix ?? ""}${c.grade ?? ""} Details`.trim();
    if (c.details_problem) d += ` · ${DETAILS_PROBLEMS[c.details_problem] ?? c.details_problem}`;
    return c.grading_service === "RAW" ? `Raw ${d}` : d;
  }
  let s = `${c.grade_prefix ?? ""}${c.grade ?? ""}`;
  if (s && c.grade_plus) s += "+";
  if (s && c.grade_star) s += "★";
  if (s && c.strike_designation) s += ` ${c.strike_designation}`;
  if (c.grading_service === "RAW") return s ? `Raw ${s}` : "Raw";
  return s || "—";
}

export const serviceLabel = (service: string) => (service === "RAW" ? "Raw" : service);

export function toningLabel(c: ToningFields): string[] {
  const t: string[] = [];
  if (c.toning_obverse) t.push("Obverse");
  if (c.toning_reverse) t.push("Reverse");
  if (c.toning_dual) t.push("Dual");
  if (c.toning_rainbow) t.push("Rainbow");
  return t;
}

export function slabLabel(c: SlabFields): string[] {
  const s: string[] = [];
  if (c.slab_soapbox) s.push("Soapbox");
  if (c.slab_ngc_fatty) s.push("NGC Fatty");
  if (c.slab_rattler) s.push("Rattler");
  if (c.slab_ogh) s.push("OGH");
  if (c.gsa_hard_pack) s.push("GSA Hard Pack");
  if (c.gsa_soft_pack) s.push("GSA Soft Pack");
  if (c.ike_blue_pack) s.push("Blue Pack");
  if (c.ike_brown_pack) s.push("Brown Pack");
  if (c.ogp) s.push("OGP");
  if (c.capital_holder) s.push("Capital Holder");
  return s;
}

export function profit(c: Coin): number | null {
  if (c.sale_price == null || c.price_paid == null) return null;
  return Number(c.sale_price) - Number(c.price_paid);
}

/** Today's date (YYYY-MM-DD) in the user's own time zone, not UTC. */
export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * A money amount as typed: "1,250", "$1250.5", " 1 250.00 " -> "1250.50". Empty -> null.
 * Anything else ("12.345", "abc", "-5") is an error, so a value is never silently dropped.
 */
export function parseMoney(text: string | number | null | undefined): { value: string | null } | { error: string } {
  const raw = String(text ?? "").trim();
  if (!raw) return { value: null };
  const noDollar = raw.replace(/[$\s]/g, "");
  // Commas only as thousands separators: "1,250.50" yes, "1,25" (a European 1.25?) no.
  if (noDollar.includes(",") && !/^\d{1,3}(,\d{3})+(\.\d*)?$/.test(noDollar)) {
    return { error: "isn't a dollar amount (use 1,250.50 or 1250.50)" };
  }
  const cleaned = noDollar.replace(/,/g, "");
  if (!/^(\d+\.?\d{0,2}|\.\d{1,2})$/.test(cleaned)) {
    return { error: /^-/.test(cleaned) ? "can't be negative" : "isn't a dollar amount (e.g. 1,250 or 1250.50)" };
  }
  // Built from the digits, not via Number(), so large amounts aren't rounded.
  const [whole, frac = ""] = cleaned.split(".");
  return { value: `${(whole || "0").replace(/^0+(?=\d)/, "")}.${frac.padEnd(2, "0")}` };
}

/** Only http(s) links from outside data (auction houses, eBay) are rendered; anything else (e.g. javascript:) isn't. */
export function safeUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url, window.location.origin);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

/** A mint or proof set's name from its catalog variety: "Main set" for the year's regular set ("Silver Proof Set"),
 * else the variation or specialty set ("Box Packaging", "Prestige Proof Set"). */
export function setLineName(variety: string | null): string {
  if (!variety) return "Main set";
  const rest = variety.replace(/^(?:\d+c |\$\d+ )?(?:Clad |Silver )?(?:Proof Set|Uncirculated Set|Special Mint Set)(?:,\s*|$)/i, "");
  return rest === variety ? variety : rest || "Main set";
}

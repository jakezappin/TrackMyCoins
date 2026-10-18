import type { BullionItem, BullionItemIn, Metal } from "./api";

export const METAL_LABEL: Record<Metal, string> = { silver: "Silver", gold: "Gold", platinum: "Platinum", palladium: "Palladium" };
export const PACKAGING_LABEL: Record<string, string> = { single: "Single", roll: "Roll", tube: "Tube", box: "Box" };
const UNIT_OZ: Record<string, number> = { ozt: 1, g: 1 / 31.1034768, kg: 1000 / 31.1034768 };
/** Junk silver: pure troy ounces per $1 face (circulated). */
export const FACE_OZ: Record<string, number> = { "0.9": 0.715, "0.4": 0.2958, "0.35": 1.1252 };
export const FACE_NOTE: Record<string, string> = {
  "0.9": "90% dimes, quarters and halves (pre-1965)",
  "0.4": "40% Kennedy halves (1965–1970)",
  "0.35": "35% war nickels (1942–1945)",
};

/** ".999", ".9999", "90%", "22k (.9167)" */
export function purityLabel(p: string | number): string {
  const n = Number(p);
  if (Math.abs(n - 0.9167) < 0.0001) return "22k (.9167)";
  if (n >= 0.99) return String(n).replace(/^0/, "");
  return `${+(n * 100).toFixed(2)}%`;
}

export function weightLabel(i: Pick<BullionItem, "weight" | "weight_unit" | "face_value">): string {
  if (i.face_value != null) return `$${Number(i.face_value).toLocaleString()} face`;
  if (i.weight == null) return "—";
  const unit = i.weight_unit === "ozt" ? "ozt" : i.weight_unit;
  return `${+Number(i.weight).toFixed(4)} ${unit}`;
}

export const ozLabel = (oz: string | number | null | undefined) => (oz == null ? "—" : `${(+Number(oz).toFixed(3)).toLocaleString()} ozt`);

/** Pure ounces from the form (matches the server's sum). */
export function pureOz(f: Pick<BullionItemIn, "weight" | "weight_unit" | "purity" | "quantity" | "face_value">): number | null {
  if (f.face_value) {
    const per = FACE_OZ[String(Number(f.purity))];
    return per ? Number(f.face_value) * per : null;
  }
  if (!f.weight || !f.purity) return null;
  return Number(f.weight) * (UNIT_OZ[f.weight_unit] ?? 1) * Number(f.purity) * (f.quantity || 1);
}

export function quantityLabel(i: Pick<BullionItem, "packaging" | "quantity" | "face_value">): string {
  if (i.face_value != null) return "Face value";
  const what = PACKAGING_LABEL[i.packaging] ?? "Single";
  return i.packaging === "single" && i.quantity === 1 ? "1 piece" : `${what} of ${i.quantity}`;
}

/** Common products: picking one fills in weight (per piece), unit, purity, or face value for junk silver.
 * Weights are gross; pure content = weight x purity (a Gold Eagle is 1.0909 ozt of 22k = 1 ozt gold). */
export interface Preset {
  name: string;
  weight?: string;
  unit?: "ozt" | "g" | "kg";
  purity: string;
  face?: boolean;
}
export const PRESETS: Record<Metal, Preset[]> = {
  silver: [
    { name: "American Silver Eagle (1 oz)", weight: "1", unit: "ozt", purity: "0.999" },
    { name: "Canadian Silver Maple Leaf (1 oz)", weight: "1", unit: "ozt", purity: "0.9999" },
    { name: "Britannia (1 oz)", weight: "1", unit: "ozt", purity: "0.999" },
    { name: "Austrian Philharmonic (1 oz)", weight: "1", unit: "ozt", purity: "0.999" },
    { name: "Mexican Libertad (1 oz)", weight: "1", unit: "ozt", purity: "0.999" },
    { name: "Generic round (1 oz)", weight: "1", unit: "ozt", purity: "0.999" },
    { name: "5 oz bar", weight: "5", unit: "ozt", purity: "0.999" },
    { name: "America the Beautiful (5 oz)", weight: "5", unit: "ozt", purity: "0.999" },
    { name: "10 oz bar", weight: "10", unit: "ozt", purity: "0.999" },
    { name: "100 oz bar", weight: "100", unit: "ozt", purity: "0.999" },
    { name: "1 kilo bar", weight: "1", unit: "kg", purity: "0.999" },
    { name: "Morgan / Peace dollar (90%)", weight: "26.73", unit: "g", purity: "0.9" },
    { name: "90% junk silver (by face value)", purity: "0.9", face: true },
    { name: "40% Kennedy halves (by face value)", purity: "0.4", face: true },
    { name: "35% war nickels (by face value)", purity: "0.35", face: true },
  ],
  gold: [
    { name: "American Gold Eagle (1 oz)", weight: "1.0909", unit: "ozt", purity: "0.9167" },
    { name: "American Gold Eagle (1/2 oz)", weight: "0.5455", unit: "ozt", purity: "0.9167" },
    { name: "American Gold Eagle (1/4 oz)", weight: "0.2727", unit: "ozt", purity: "0.9167" },
    { name: "American Gold Eagle (1/10 oz)", weight: "0.1091", unit: "ozt", purity: "0.9167" },
    { name: "American Gold Buffalo (1 oz)", weight: "1", unit: "ozt", purity: "0.9999" },
    { name: "Canadian Gold Maple Leaf (1 oz)", weight: "1", unit: "ozt", purity: "0.9999" },
    { name: "South African Krugerrand (1 oz)", weight: "1.0909", unit: "ozt", purity: "0.9167" },
    { name: "Gold Britannia (1 oz)", weight: "1", unit: "ozt", purity: "0.9999" },
    { name: "Gold Philharmonic (1 oz)", weight: "1", unit: "ozt", purity: "0.9999" },
    { name: "1 oz gold bar", weight: "1", unit: "ozt", purity: "0.9999" },
    { name: "10 gram gold bar", weight: "10", unit: "g", purity: "0.9999" },
    { name: "1 kilo gold bar", weight: "1", unit: "kg", purity: "0.9999" },
    { name: "$20 Liberty / Saint-Gaudens (pre-1933)", weight: "33.436", unit: "g", purity: "0.9" },
    { name: "$10 Liberty / Indian (pre-1933)", weight: "16.718", unit: "g", purity: "0.9" },
    { name: "$5 Liberty / Indian (pre-1933)", weight: "8.359", unit: "g", purity: "0.9" },
  ],
  platinum: [
    { name: "American Platinum Eagle (1 oz)", weight: "1", unit: "ozt", purity: "0.9995" },
    { name: "Canadian Platinum Maple Leaf (1 oz)", weight: "1", unit: "ozt", purity: "0.9995" },
    { name: "1 oz platinum bar", weight: "1", unit: "ozt", purity: "0.9995" },
  ],
  palladium: [
    { name: "American Palladium Eagle (1 oz)", weight: "1", unit: "ozt", purity: "0.9995" },
    { name: "Canadian Palladium Maple Leaf (1 oz)", weight: "1", unit: "ozt", purity: "0.9995" },
    { name: "1 oz palladium bar", weight: "1", unit: "ozt", purity: "0.9995" },
  ],
};

/** "92.5%", ".925", "925", "0.925" -> "0.925"; null if it isn't a purity. */
export function parsePurity(text: string): string | null {
  const t = text.trim().replace(/\s|fine/gi, "");
  if (!t) return null;
  let n = t.endsWith("%") ? Number(t.slice(0, -1)) / 100 : Number(t);
  if (!Number.isFinite(n) || n <= 0) return null;
  while (n > 1) n /= n >= 100 ? 1000 : n >= 10 ? 100 : 10;
  return n > 0 && n <= 1 ? String(+n.toFixed(5)) : null;
}

/** "2 yr 3 mo" / "5 mo" / "12 days" */
export function heldLabel(days: number): string {
  if (days < 31) return `${days} day${days === 1 ? "" : "s"}`;
  const months = Math.floor(days / 30.44);
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y && `${y} yr`, m && `${m} mo`].filter(Boolean).join(" ") || "1 mo";
}

/** Long-term (held more than a year) or short-term, for U.S. taxes on a sale. */
export const termLabel = (i: { long_term: boolean; held_days: number }) =>
  `${i.long_term ? "Long-term" : "Short-term"} · held ${heldLabel(i.held_days)}`;

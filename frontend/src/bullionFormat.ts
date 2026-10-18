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

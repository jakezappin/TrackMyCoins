import { SOLD_VIA, type SoldVia } from "../api";

/** "Sold via": where it was sold (Dealer, eBay, Coin Show...), with a box to describe Other. */
export default function SoldViaField({
  via,
  other,
  onChange,
  includeTrade = true,
}: {
  via: SoldVia | null | undefined;
  other: string | null | undefined;
  onChange: (via: SoldVia | null, other: string | null) => void;
  /** Trades are recorded in the Sales Tracker; a coin already traded still shows Trade here. */
  includeTrade?: boolean;
}) {
  const options = SOLD_VIA.filter(([v]) => includeTrade || v !== "trade" || via === "trade");
  return (
    <div className="sold-via">
      <label className="field">
        <span>Sold via</span>
        <select value={via ?? ""} onChange={(e) => onChange((e.target.value || null) as SoldVia | null, other ?? null)}>
          <option value="">Choose…</option>
          {options.map(([v, label]) => (
            <option key={v} value={v}>
              {v === "other" ? "Other (specify)" : label}
            </option>
          ))}
        </select>
      </label>
      {via === "other" && (
        <label className="field">
          <span>Where</span>
          <input
            value={other ?? ""}
            onChange={(e) => onChange("other", e.target.value || null)}
            placeholder="Facebook group, club auction…"
            maxLength={60}
          />
        </label>
      )}
    </div>
  );
}

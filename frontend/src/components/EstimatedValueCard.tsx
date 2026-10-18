import { useEffect, useRef, useState } from "react";
import { api, type CoinDetail } from "../api";
import { money, parseMoney } from "../format";

type PremiumKey = "toner" | "holder";
const PREMIUMS: { key: PremiumKey; label: string; hint: string }[] = [
  { key: "toner", label: "Toner premium", hint: "Extra for attractive toning" },
  { key: "holder", label: "Holder premium", hint: "Extra for a Rattler, Fatty, OGH, GSA or other desirable holder" },
];

/** The coin's estimated value: CPG plus optional toner/holder premiums, or the owner's own figure. */
export default function EstimatedValueCard({ coin, onChange }: { coin: CoinDetail; onChange: (c: CoinDetail) => void }) {
  const saved = { toner: coin.toner_premium ?? "", holder: coin.holder_premium ?? "" };
  const [source, setSource] = useState<"cpg" | "custom">(coin.value_source);
  const [on, setOn] = useState({ toner: Boolean(coin.toner_premium), holder: Boolean(coin.holder_premium) });
  const [amount, setAmount] = useState(saved);
  const [custom, setCustom] = useState(coin.custom_value ?? "");
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSource(coin.value_source);
    setOn({ toner: Boolean(coin.toner_premium), holder: Boolean(coin.holder_premium) });
    setAmount({ toner: coin.toner_premium ?? "", holder: coin.holder_premium ?? "" });
    setCustom(coin.custom_value ?? "");
  }, [coin.value_source, coin.toner_premium, coin.holder_premium, coin.custom_value]);

  // A Details coin's CPG-based value is its share of the straight-grade CPG.
  const cpg = coin.details ? coin.details_value : coin.latest_cpg?.value ?? null;
  const premium = (k: PremiumKey) => (on[k] && amount[k] ? amount[k] : "");
  const amt = (t: string) => {
    const r = parseMoney(t);
    return "value" in r && r.value !== null ? Number(r.value) : null;
  };
  const preview =
    source === "custom"
      ? amt(custom)
      : cpg != null
        ? Number(cpg) + (amt(premium("toner")) ?? 0) + (amt(premium("holder")) ?? 0)
        : null;
  const dirty =
    source !== coin.value_source ||
    (source === "custom" && custom !== (coin.custom_value ?? "")) ||
    (source === "cpg" && (premium("toner") !== saved.toner || premium("holder") !== saved.holder));

  function reset() {
    setSource(coin.value_source);
    setOn({ toner: Boolean(coin.toner_premium), holder: Boolean(coin.holder_premium) });
    setAmount(saved);
    setCustom(coin.custom_value ?? "");
    setError(null);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (saving.current) return; // ignore a second tap while saving
    // "1,250" and "$1250" are fine; anything unreadable is reported instead of being dropped.
    const fields: [string, string][] =
      source === "custom" ? [["Your estimated value", custom]] : [["Toner premium", premium("toner")], ["Holder premium", premium("holder")]];
    const parsed: Record<string, string | null> = {};
    for (const [label, text] of fields) {
      const r = parseMoney(text);
      if ("error" in r) {
        setError(`${label} ${r.error}.`);
        return;
      }
      parsed[label] = r.value;
    }
    saving.current = true;
    setBusy(true);
    setError(null);
    try {
      onChange(
        await api.setValuation(coin.inventory_number, {
          source,
          custom_value: source === "custom" ? parsed["Your estimated value"] : null,
          toner_premium: source === "cpg" ? parsed["Toner premium"] : null,
          holder_premium: source === "cpg" ? parsed["Holder premium"] : null,
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  const breakdown = [
    cpg ? `${coin.details ? "Details value" : "CPG"} ${money(cpg)}` : null,
    coin.toner_premium ? `toner premium ${money(coin.toner_premium)}` : null,
    coin.holder_premium ? `holder premium ${money(coin.holder_premium)}` : null,
  ].filter(Boolean);

  return (
    <section className="card">
      <h2>Estimated Value</h2>
      <div className="big-number">{money(coin.value_estimate)}</div>
      <p className="muted small">
        {coin.value_source === "custom"
          ? "Your own value"
          : cpg
            ? breakdown.length > 1
              ? breakdown.join(" + ")
              : coin.details
                ? "From CPG, as a Details coin"
                : "From CPG"
            : "Get a CPG price or enter your own value"}
        . Used in your collection totals.
      </p>

      <form className="stack value-form" onSubmit={save}>
        <div className="segmented" role="radiogroup" aria-label="Value source">
          {(
            [
              ["cpg", "From CPG"],
              ["custom", "My own value"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={source === v}
              className={`seg ${source === v ? "active" : ""}`}
              onClick={() => setSource(v)}
            >
              {label}
            </button>
          ))}
        </div>

        {source === "cpg" ? (
          <div className="premium-boxes">
            {PREMIUMS.map(({ key, label, hint }) => (
              <div key={key} className={`premium-box ${on[key] ? "on" : ""}`}>
                <label className="checks" title={hint}>
                  <span>
                    <input type="checkbox" checked={on[key]} onChange={(e) => setOn({ ...on, [key]: e.target.checked })} />{" "}
                    {label}
                  </span>
                </label>
                {on[key] && (
                  <input
                    type="text"
                    inputMode="decimal"
                    value={amount[key]}
                    onChange={(e) => setAmount({ ...amount, [key]: e.target.value })}
                    placeholder="0.00"
                    aria-label={`${label} amount`}
                    required
                  />
                )}
              </div>
            ))}
          </div>
        ) : (
          <label className="field">
            <span>Your estimated value</span>
            <input type="text" inputMode="decimal" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="0.00" required />
          </label>
        )}

        {dirty && (
          <div className="card-foot">
            <span className="small">
              <span className="muted">New value</span> <strong>{money(preview)}</strong>
            </span>
            <div className="row">
              <button type="button" className="btn" disabled={busy} onClick={reset}>
                Cancel
              </button>
              <button className="btn btn-primary" disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        )}
        {error && <p className="error small">{error}</p>}
      </form>
      {coin.details && coin.details_basis && <DetailsNote basis={coin.details_basis} />}
    </section>
  );
}

/** How a Details (problem) coin is priced: shown at the foot of the value cards. */
export function DetailsNote({ basis }: { basis: string }) {
  return (
    <p className="details-note small">
      <span className="details-badge">Details</span> {basis} Change the default % in Account settings, or set this
      coin's own on its edit page.
    </p>
  );
}

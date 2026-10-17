import { useEffect, useState } from "react";
import { api, type CoinDetail } from "../api";
import { money } from "../format";

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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSource(coin.value_source);
    setOn({ toner: Boolean(coin.toner_premium), holder: Boolean(coin.holder_premium) });
    setAmount({ toner: coin.toner_premium ?? "", holder: coin.holder_premium ?? "" });
    setCustom(coin.custom_value ?? "");
  }, [coin.value_source, coin.toner_premium, coin.holder_premium, coin.custom_value]);

  const cpg = coin.latest_cpg?.value ?? null;
  const premium = (k: PremiumKey) => (on[k] && amount[k] ? amount[k] : "");
  const preview =
    source === "custom"
      ? custom || null
      : cpg != null
        ? String(Number(cpg) + Number(premium("toner") || 0) + Number(premium("holder") || 0))
        : null;
  const dirty =
    source !== coin.value_source ||
    (source === "custom" && custom !== (coin.custom_value ?? "")) ||
    (source === "cpg" && (premium("toner") !== saved.toner || premium("holder") !== saved.holder));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onChange(
        await api.setValuation(coin.inventory_number, {
          source,
          custom_value: source === "custom" ? custom : null,
          toner_premium: source === "cpg" ? premium("toner") || null : null,
          holder_premium: source === "cpg" ? premium("holder") || null : null,
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const breakdown = [
    cpg ? `CPG ${money(cpg)}` : null,
    coin.toner_premium ? `toner premium ${money(coin.toner_premium)}` : null,
    coin.holder_premium ? `holder premium ${money(coin.holder_premium)}` : null,
  ].filter(Boolean);

  return (
    <section className="card">
      <h2>Estimated value</h2>
      <div className="big-number">{money(coin.value_estimate)}</div>
      <p className="muted small">
        {coin.value_source === "custom"
          ? "Your own value"
          : cpg
            ? breakdown.length > 1
              ? breakdown.join(" + ")
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
                    type="number"
                    step="0.01"
                    min={0}
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
            <input type="number" step="0.01" min={0} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="0.00" required />
          </label>
        )}

        {dirty && (
          <div className="row">
            <span className="muted small">New value: {money(preview)}</span>
            <button className="btn btn-primary" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        )}
        {error && <p className="error small">{error}</p>}
      </form>
    </section>
  );
}

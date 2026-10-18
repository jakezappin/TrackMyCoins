import { useEffect, useRef, useState } from "react";
import { api, type CoinDetail } from "../api";
import { money, parseMoney } from "../format";

type PremiumKey = "toner" | "holder" | "lowball";
const PREMIUMS: { key: PremiumKey; label: string; hint: string }[] = [
  { key: "toner", label: "Toner Premium", hint: "Extra for attractive toning" },
  { key: "holder", label: "Holder Premium", hint: "Extra for a Rattler, Fatty, OGH, GSA or other desirable holder" },
  { key: "lowball", label: "Lowball Premium", hint: "Extra for a low-grade coin collectors want, e.g. a PO1 or FR2 for lowball sets" },
];
const KEYS: PremiumKey[] = ["toner", "holder", "lowball"];
const FIELD = { toner: "toner_premium", holder: "holder_premium", lowball: "lowball_premium" } as const;

/** The coin's estimated value: CPG plus optional toner, holder and lowball premiums, or the owner's own figure. */
export default function EstimatedValueCard({ coin, onChange }: { coin: CoinDetail; onChange: (c: CoinDetail) => void }) {
  const savedOf = () => ({ toner: coin.toner_premium ?? "", holder: coin.holder_premium ?? "", lowball: coin.lowball_premium ?? "" });
  const onOf = () => ({ toner: Boolean(coin.toner_premium), holder: Boolean(coin.holder_premium), lowball: Boolean(coin.lowball_premium) });
  const saved = savedOf();
  const own = coin.is_error ? "custom" : coin.value_source; // error coins have only the owner's value
  const [source, setSource] = useState<"cpg" | "custom">(own);
  const [on, setOn] = useState(onOf);
  const [amount, setAmount] = useState(saved);
  const [custom, setCustom] = useState(coin.custom_value ?? "");
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSource(own);
    setOn(onOf());
    setAmount(savedOf());
    setCustom(coin.custom_value ?? "");
  }, [coin.value_source, coin.toner_premium, coin.holder_premium, coin.lowball_premium, coin.custom_value, coin.is_error]); // eslint-disable-line react-hooks/exhaustive-deps

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
        ? Number(cpg) + KEYS.reduce((t, k) => t + (amt(premium(k)) ?? 0), 0)
        : null;
  const dirty =
    source !== own ||
    (source === "custom" && custom !== (coin.custom_value ?? "")) ||
    (source === "cpg" && KEYS.some((k) => premium(k) !== saved[k]));

  function reset() {
    setSource(own);
    setOn(onOf());
    setAmount(saved);
    setCustom(coin.custom_value ?? "");
    setError(null);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (saving.current) return; // ignore a second tap while saving
    // "1,250" and "$1250" are fine; anything unreadable is reported instead of being dropped.
    const fields: [string, string][] =
      source === "custom" ? [["Your estimated value", custom]] : PREMIUMS.map((p) => [p.label, premium(p.key)] as [string, string]);
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
          ...Object.fromEntries(PREMIUMS.map((p) => [FIELD[p.key], source === "cpg" ? parsed[p.label] : null])),
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
    coin.lowball_premium ? `lowball premium ${money(coin.lowball_premium)}` : null,
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
          ).filter(([v]) => !(coin.is_error && v === "cpg")) // error coins: only your own value
          .map(([v, label]) => (
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
      {coin.is_error && (
        <p className="muted small">Error coins aren't in the price guides, so their value is the one you enter.</p>
      )}
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

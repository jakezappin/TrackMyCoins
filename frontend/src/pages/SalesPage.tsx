import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { api, soldViaLabel, SOLD_VIA, type CoinFields, type GradingService, type SaleEntry, type SaleItem, type SoldVia } from "../api";
import { useApp } from "../App";
import DealerInput from "../components/DealerInput";
import SoldViaField from "../components/SoldViaField";
import { collectionsBySeries, money, parseMoney, shortDate, todayISO } from "../format";
import { SHELDON_NUMBERS, letterGrade } from "../sheldon";

const cents = (v: string | number | null | undefined) => Math.round(Number(v ?? 0) * 100);
const dollars = (c: number) => (c / 100).toFixed(2);

/** `total` cents across items by `weights` (equally if all 0); the last takes the rounding so they add up. */
function split(total: number, weights: number[]): number[] {
  const sum = weights.reduce((a, b) => a + b, 0);
  const shares = sum > 0 ? weights.map((w) => w / sum) : weights.map(() => 1 / weights.length);
  const parts = shares.slice(0, -1).map((s) => Math.round(total * s));
  return [...parts, total - parts.reduce((a, b) => a + b, 0)];
}

/** Sell or trade coins and bullion from one page, and see every sale and trade. */
export default function SalesPage() {
  const [entries, setEntries] = useState<SaleEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<SaleItem[]>([]);
  const [dialog, setDialog] = useState<"sale" | "trade" | null>(null);
  const [pickerKey, setPickerKey] = useState(0);
  const { refresh } = useApp();

  const load = () =>
    api
      .sales()
      .then(setEntries)
      .catch((e) => setError((e as Error).message));
  useEffect(() => {
    load();
  }, []);

  function done() {
    setDialog(null);
    setPicked([]);
    setPickerKey((k) => k + 1);
    load();
    refresh();
  }

  return (
    <div className="page sales-page">
      <div className="page-head">
        <div>
          <h1>Sales Tracker</h1>
          <p className="muted small">Pick the coins or bullion you sold or traded, then record it. Each item's sale shows on its own page too.</p>
        </div>
      </div>

      <section className="card">
        <h2>Record a Sale or Trade</h2>
        <ItemPicker key={pickerKey} picked={picked} onChange={setPicked} />
        {picked.length > 0 && (
          <div className="sales-picked">
            <ul className="chip-list">
              {picked.map((i) => (
                <li key={i.ref} className="chip">
                  {i.inventory_number} · {i.title}
                  <button type="button" aria-label={`Remove ${i.inventory_number}`} onClick={() => setPicked(picked.filter((p) => p.ref !== i.ref))}>
                    ✕
                  </button>
                </li>
              ))}
            </ul>
            <div className="row">
              <button className="btn btn-primary" onClick={() => setDialog("sale")}>
                Record sale ({picked.length})
              </button>
              <button className="btn" onClick={() => setDialog("trade")}>
                Record trade ({picked.length})
              </button>
            </div>
          </div>
        )}
      </section>

      {error && <p className="error">{error}</p>}
      {!entries && !error && <p className="muted">Loading…</p>}
      {entries && <History entries={entries} onChanged={() => (load(), refresh())} />}

      {dialog === "sale" && <SaleDialog items={picked} onClose={() => setDialog(null)} onDone={done} />}
      {dialog === "trade" && <TradeDialog out={picked} onClose={() => setDialog(null)} onDone={done} />}
    </div>
  );
}

/** Search on-hand coins and bullion and tick the ones to sell or trade. */
function ItemPicker({
  picked,
  onChange,
  exclude = [],
  placeholder = "Search by date, series, variety, cert or inventory #…",
}: {
  picked: SaleItem[];
  onChange: (items: SaleItem[]) => void;
  exclude?: string[];
  placeholder?: string;
}) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<SaleItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api
        .saleItems(q)
        .then((r) => live && (setFound(r), setError(null)))
        .catch((e) => live && setError((e as Error).message));
    }, 200);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q]);

  const has = (i: SaleItem) => picked.some((p) => p.ref === i.ref);
  const shown = (found ?? []).filter((i) => !exclude.includes(i.ref));
  return (
    <div className="item-picker">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label="Search your items" />
      {error && <p className="error small">{error}</p>}
      {found && (
        <ul className="item-picker-list">
          {shown.length === 0 && <li className="muted small">Nothing on hand matches.</li>}
          {shown.map((i) => (
            <li key={i.ref}>
              <label className="check item-picker-row">
                <input type="checkbox" checked={has(i)} onChange={() => onChange(has(i) ? picked.filter((p) => p.ref !== i.ref) : [...picked, i])} />
                {i.thumb_url ? <img src={i.thumb_url} alt="" className="item-thumb" /> : <span className="item-thumb blank" />}
                <span className="item-picker-main">
                  <strong>{i.title}</strong>
                  <span className="muted small">
                    {i.inventory_number} · {i.collection_name}
                  </span>
                </span>
                <span className="small muted num">
                  {i.est_value != null ? `Worth ${money(i.est_value)}` : ""}
                  {i.price_paid != null ? <><br />Paid {money(i.price_paid)}</> : null}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Modal({ title, wide, onClose, children }: { title: string; wide?: boolean; onClose: () => void; children: React.ReactNode }) {
  return createPortal(
    <div className="modal-backdrop">
      <div className={`modal${wide ? " modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/** Who, when (and for a sale, where). */
function PartyFields({
  day,
  setDay,
  who,
  dealerId,
  setWho,
  label,
}: {
  day: string;
  setDay: (d: string) => void;
  who: string | null;
  dealerId: number | null;
  setWho: (t: string | null, id: number | null) => void;
  label: string;
}) {
  return (
    <>
      <label className="field">
        <span>Date</span>
        <input type="date" max={todayISO()} value={day} onChange={(e) => setDay(e.target.value)} />
      </label>
      <label className="field">
        <span>{label}</span>
        <DealerInput text={who} dealerId={dealerId} onChange={setWho} />
      </label>
    </>
  );
}

/** Price lines: one per item, edited directly. */
function PriceLines({ items, prices, setPrice, label }: { items: SaleItem[]; prices: string[]; setPrice: (i: number, v: string) => void; label: string }) {
  return (
    <table className="price-lines">
      <thead>
        <tr>
          <th>Item</th>
          <th className="num">Paid</th>
          <th className="num">Worth</th>
          <th className="num">{label}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((it, n) => (
          <tr key={it.ref}>
            <td>
              {it.title}
              <div className="muted small">{it.inventory_number}</div>
            </td>
            <td className="num small">{money(it.price_paid)}</td>
            <td className="num small">{money(it.est_value)}</td>
            <td className="num">
              <input inputMode="decimal" value={prices[n] ?? ""} onChange={(e) => setPrice(n, e.target.value)} aria-label={`${label} for ${it.inventory_number}`} placeholder="0.00" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function checkPrices(prices: string[], items: SaleItem[]): string | null {
  for (let n = 0; n < items.length; n++) {
    const p = parseMoney(prices[n]);
    if ("error" in p || p.value == null) return `${items[n].inventory_number}: enter a dollar amount.`;
  }
  return null;
}

function SaleDialog({ items, onClose, onDone }: { items: SaleItem[]; onClose: () => void; onDone: () => void }) {
  const [day, setDay] = useState(todayISO());
  const [via, setVia] = useState<SoldVia | null>(null);
  const [viaOther, setViaOther] = useState<string | null>(null);
  const [who, setWho] = useState<string | null>(null);
  const [dealerId, setDealerId] = useState<number | null>(null);
  const [total, setTotal] = useState("");
  const [prices, setPrices] = useState<string[]>(items.map(() => ""));
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const one = items.length === 1;

  // The total, split by what each item is worth now (editable per item).
  function setTotalText(t: string) {
    setTotal(t);
    const p = parseMoney(t);
    if ("error" in p || p.value == null) return;
    setPrices(split(cents(p.value), items.map((i) => cents(i.est_value ?? i.price_paid))).map(dollars));
  }
  function setPrice(n: number, v: string) {
    const next = prices.map((p, k) => (k === n ? v : p));
    setPrices(next);
    if (next.every((x) => x.trim() && !("error" in parseMoney(x)))) setTotal(dollars(next.reduce((a, x) => a + cents(x), 0)));
  }

  async function save() {
    const bad = one ? (parseMoney(total) as { value: string | null }).value == null && "Enter the sale price." : checkPrices(prices, items);
    if (bad) return setError(bad);
    if (!day) return setError("Enter the date.");
    setBusy(true);
    setError(null);
    try {
      await api.recordSale({
        sale_date: day,
        sold_via: via ?? (dealerId ? "dealer" : null),
        sold_via_other: via === "other" ? viaOther : null,
        counterparty: who,
        dealer_id: dealerId,
        notes: notes.trim() || null,
        items: items.map((i, n) => ({ ref: i.ref, price: one ? (parseMoney(total) as { value: string }).value : (parseMoney(prices[n]) as { value: string }).value })),
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title={one ? `Sell ${items[0].inventory_number}` : `Sell ${items.length} Items`} wide={!one} onClose={onClose}>
      <div className="grid-2">
        <PartyFields day={day} setDay={setDay} who={who} dealerId={dealerId} setWho={(t, id) => (setWho(t), setDealerId(id))} label={via === "dealer" ? "Dealer" : "Sold to"} />
        <SoldViaField via={via} other={viaOther} includeTrade={false} onChange={(v, o) => (setVia(v), setViaOther(o))} />
        <label className="field">
          <span>{one ? "Sale price" : "Total sale price"}</span>
          <input inputMode="decimal" value={total} onChange={(e) => (one ? setTotal(e.target.value) : setTotalText(e.target.value))} placeholder="0.00" autoFocus />
          {!one && <small className="muted">Split by what each is worth now. Change any item's share below.</small>}
        </label>
      </div>
      {!one && <PriceLines items={items} prices={prices} setPrice={setPrice} label="Sale price" />}
      <label className="field">
        <span>Notes (optional)</span>
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} />
      </label>
      {error && <p className="error small">{error}</p>}
      <div className="row-end">
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Record sale"}
        </button>
      </div>
    </Modal>
  );
}

function TradeDialog({ out, onClose, onDone }: { out: SaleItem[]; onClose: () => void; onDone: () => void }) {
  const [day, setDay] = useState(todayISO());
  const [who, setWho] = useState<string | null>(null);
  const [dealerId, setDealerId] = useState<number | null>(null);
  const [outValues, setOutValues] = useState<string[]>(out.map((i) => (i.est_value != null ? Number(i.est_value).toFixed(2) : "")));
  const [cameIn, setCameIn] = useState<SaleItem[]>([]);
  const [inValues, setInValues] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<string[]>([]); // coins added in this trade (deleted again if it's cancelled)
  const [cashIn, setCashIn] = useState("");
  const [cashOut, setCashOut] = useState("");
  const [notes, setNotes] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addIn = (items: SaleItem[]) => {
    setCameIn(items);
    setInValues((v) => {
      const next = { ...v };
      for (const i of items) if (next[i.ref] == null) next[i.ref] = i.est_value != null ? Number(i.est_value).toFixed(2) : "";
      return next;
    });
  };

  // What came in costs what was given: trade values out + cash paid − cash received, split by their trade values.
  const given = outValues.reduce((a, v) => a + cents(v), 0) + cents(cashOut) - cents(cashIn);
  const costs = cameIn.length ? split(Math.max(given, 0), cameIn.map((i) => cents(inValues[i.ref]))) : [];

  async function cancel() {
    if (created.length && confirm(`Delete the ${created.length} coin${created.length === 1 ? "" : "s"} you added for this trade?`)) {
      await Promise.all(created.map((inv) => api.deleteCoin(inv).catch(() => undefined)));
    }
    onClose();
  }

  async function save() {
    const bad = checkPrices(outValues, out) ?? checkPrices(cameIn.map((i) => inValues[i.ref] ?? ""), cameIn);
    if (bad) return setError(bad);
    if (!cameIn.length) return setError("Add what you got in the trade.");
    for (const [label, v] of [["Cash received", cashIn], ["Cash paid", cashOut]] as const)
      if (v.trim() && "error" in parseMoney(v)) return setError(`${label}: enter a dollar amount.`);
    setBusy(true);
    setError(null);
    try {
      await api.recordTrade({
        sale_date: day,
        counterparty: who,
        dealer_id: dealerId,
        notes: notes.trim() || null,
        out: out.map((i, n) => ({ ref: i.ref, price: dollars(cents(outValues[n])) })),
        came_in: cameIn.map((i) => ({ ref: i.ref, price: dollars(cents(inValues[i.ref])) })),
        cash_received: cashIn.trim() ? dollars(cents(cashIn)) : null,
        cash_paid: cashOut.trim() ? dollars(cents(cashOut)) : null,
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Record Trade" wide onClose={cancel}>
      <div className="grid-2">
        <PartyFields day={day} setDay={setDay} who={who} dealerId={dealerId} setWho={(t, id) => (setWho(t), setDealerId(id))} label="Traded with" />
      </div>

      <h3 className="details-sub">You Gave</h3>
      <PriceLines items={out} prices={outValues} setPrice={(n, v) => setOutValues(outValues.map((x, k) => (k === n ? v : x)))} label="Trade value" />
      <p className="muted small">Each item's trade value is its sale price. It starts at what it's worth now.</p>

      <h3 className="details-sub">You Got</h3>
      {cameIn.length > 0 && (
        <table className="price-lines">
          <thead>
            <tr>
              <th>Item</th>
              <th className="num">Trade value</th>
              <th className="num">Cost to you</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cameIn.map((it, n) => (
              <tr key={it.ref}>
                <td>
                  {it.title}
                  <div className="muted small">{it.inventory_number}</div>
                </td>
                <td className="num">
                  <input inputMode="decimal" value={inValues[it.ref] ?? ""} onChange={(e) => setInValues({ ...inValues, [it.ref]: e.target.value })} aria-label={`Trade value for ${it.inventory_number}`} placeholder="0.00" />
                </td>
                <td className="num small">{money(dollars(costs[n] ?? 0))}</td>
                <td>
                  <button type="button" className="icon-btn" aria-label={`Remove ${it.inventory_number}`} onClick={() => addIn(cameIn.filter((x) => x.ref !== it.ref))}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="row">
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          + New coin
        </button>
        <details className="trade-existing">
          <summary className="small">Or pick one you've already entered</summary>
          <ItemPicker picked={cameIn} onChange={addIn} exclude={out.map((i) => i.ref)} placeholder="Search coins and bullion you've entered…" />
        </details>
      </div>

      <div className="grid-2">
        <label className="field">
          <span>Cash you received (optional)</span>
          <input inputMode="decimal" value={cashIn} onChange={(e) => setCashIn(e.target.value)} placeholder="0.00" />
        </label>
        <label className="field">
          <span>Cash you paid (optional)</span>
          <input inputMode="decimal" value={cashOut} onChange={(e) => setCashOut(e.target.value)} placeholder="0.00" />
        </label>
      </div>
      {cameIn.length > 0 && (
        <p className="small">
          You gave {money(dollars(outValues.reduce((a, v) => a + cents(v), 0)))} in trade
          {cents(cashOut) ? ` plus ${money(dollars(cents(cashOut)))} cash` : ""}
          {cents(cashIn) ? `, less ${money(dollars(cents(cashIn)))} cash back` : ""}, so what you got cost{" "}
          <strong>{money(dollars(Math.max(given, 0)))}</strong>, split by trade value.
        </p>
      )}
      <label className="field">
        <span>Notes (optional)</span>
        <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} />
      </label>
      {error && <p className="error small">{error}</p>}
      <div className="row-end">
        <button type="button" className="btn" onClick={cancel} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Record trade"}
        </button>
      </div>

      {adding && (
        <NewCoinDialog
          day={day}
          onClose={() => setAdding(false)}
          onAdded={(item, value) => {
            setAdding(false);
            setCreated((c) => [...c, item.inventory_number]);
            setCameIn((c) => [...c, item]);
            setInValues((v) => ({ ...v, [item.ref]: value }));
          }}
        />
      )}
    </Modal>
  );
}

const SERVICES: GradingService[] = ["PCGS", "NGC", "ANACS", "CACG", "ICG", "OTHER", "RAW"];

/** A coin that came in a trade: just enough to identify it. The rest can be filled in on its page later. */
function NewCoinDialog({ day, onClose, onAdded }: { day: string; onClose: () => void; onAdded: (item: SaleItem, value: string) => void }) {
  const { coinTypes, collections } = useApp();
  const groups = useMemo(() => collectionsBySeries(coinTypes, collections), [coinTypes, collections]);
  const [collectionId, setCollectionId] = useState<number | "">(collections[0]?.id ?? "");
  const [year, setYear] = useState("");
  const [mint, setMint] = useState("P");
  const [service, setService] = useState<GradingService>("PCGS");
  const [cert, setCert] = useState("");
  const [grade, setGrade] = useState<number | "">("");
  const [variety, setVariety] = useState("");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const col = collections.find((c) => c.id === collectionId);
  const proof = col ? col.finish !== "MS" : false;

  async function add() {
    if (!collectionId) return setError("Pick a collection.");
    if (!/^\d{4}$/.test(year.trim())) return setError("Enter the year, like 1881.");
    const v = parseMoney(value);
    if ("error" in v || v.value == null) return setError("Enter its trade value.");
    setBusy(true);
    setError(null);
    try {
      const body = {
        collection_id: collectionId,
        year: Number(year),
        mint_mark: mint.trim() || "P",
        grading_service: service,
        cert_number: service === "RAW" ? null : cert.trim() || null,
        grade: grade === "" ? null : grade,
        grade_prefix: grade === "" ? null : proof ? "PR" : letterGrade(grade),
        variety: variety.trim() || null,
        purchase_date: day,
      } as unknown as CoinFields & { collection_id: number };
      const c = await api.createCoin(body);
      const [item] = await api.saleItems(c.inventory_number);
      onAdded(item, v.value);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Coin You Got" onClose={onClose}>
      <p className="muted small">Just the basics. Add photos and the rest on the coin's page later.</p>
      <label className="field">
        <span>Collection</span>
        <select value={collectionId} onChange={(e) => setCollectionId(e.target.value ? Number(e.target.value) : "")}>
          {groups.map(({ type, collections: cols }) => (
            <optgroup key={type.id} label={type.plural}>
              {cols.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      <div className="grid-2">
        <label className="field">
          <span>Year</span>
          <input inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} placeholder="1881" maxLength={4} autoFocus />
        </label>
        <label className="field">
          <span>Mint</span>
          <input value={mint} onChange={(e) => setMint(e.target.value.toUpperCase())} placeholder="P, S, O, CC…" maxLength={3} />
        </label>
        <label className="field">
          <span>Grading</span>
          <select value={service} onChange={(e) => setService(e.target.value as GradingService)}>
            {SERVICES.map((s) => (
              <option key={s} value={s}>
                {s === "RAW" ? "Raw (ungraded)" : s === "OTHER" ? "Other Grading Service" : s}
              </option>
            ))}
          </select>
        </label>
        {service !== "RAW" && (
          <label className="field">
            <span>Cert number</span>
            <input value={cert} onChange={(e) => setCert(e.target.value)} />
          </label>
        )}
        <label className="field">
          <span>Grade{service === "RAW" ? " (optional)" : ""}</span>
          <select value={grade} onChange={(e) => setGrade(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Grade…</option>
            {SHELDON_NUMBERS.slice()
              .reverse()
              .map((n) => (
                <option key={n} value={n}>
                  {proof ? "PR" : letterGrade(n)}
                  {n}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          <span>Variety (optional)</span>
          <input value={variety} onChange={(e) => setVariety(e.target.value)} placeholder="VAM 3, 8TF…" />
        </label>
        <label className="field">
          <span>Trade value</span>
          <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="0.00" />
        </label>
      </div>
      {error && <p className="error small">{error}</p>}
      <div className="row-end">
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={add} disabled={busy}>
          {busy ? "Adding…" : "Add coin"}
        </button>
      </div>
    </Modal>
  );
}

/** Every sale and trade, filtered, with totals by where it was sold. */
function History({ entries, onChanged }: { entries: SaleEntry[]; onChanged: () => void }) {
  const [q, setQ] = useState("");
  const [via, setVia] = useState<string>("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [collectionId, setCollectionId] = useState<string>("");

  const term = q.trim().toLowerCase();
  const shown = entries.filter((e) => {
    if (via && (e.sold_via ?? "none") !== via) return false;
    if (from && e.sale_date < from) return false;
    if (to && e.sale_date > to) return false;
    if (collectionId && ![...e.out, ...e.in].some((i) => String(i.collection_id) === collectionId.split(":")[1] && i.kind === collectionId.split(":")[0]))
      return false;
    if (term) {
      const hay = [e.counterparty, e.notes, soldViaLabel(e.sold_via, e.sold_via_other), ...[...e.out, ...e.in].flatMap((i) => [i.title, i.inventory_number])]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!term.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  });

  // Totals by channel over what's shown.
  const byVia = new Map<string, { label: string; count: number; total: number; profit: number; hasProfit: boolean }>();
  for (const e of shown) {
    const key = e.sold_via ?? "none";
    const row = byVia.get(key) ?? { label: soldViaLabel(e.sold_via, null) ?? "Not specified", count: 0, total: 0, profit: 0, hasProfit: false };
    row.count += e.out.length;
    row.total += cents(e.total);
    if (e.profit != null) (row.profit += cents(e.profit)), (row.hasProfit = true);
    byVia.set(key, row);
  }
  const usedCollections = new Map<string, string>();
  for (const e of entries) for (const i of [...e.out, ...e.in]) usedCollections.set(`${i.kind}:${i.collection_id}`, i.collection_name);

  async function undo(e: SaleEntry) {
    if (e.id == null) return;
    const what = e.kind === "trade" ? "trade" : "sale";
    if (!confirm(`Undo this ${what}? ${e.out.length === 1 ? "The item goes" : "The items go"} back to on hand.`)) return;
    const del = e.kind === "trade" && e.in.length > 0 && confirm(`Also delete the ${e.in.length} item${e.in.length === 1 ? "" : "s"} you got in the trade? Cancel keeps them.`);
    try {
      await api.deleteSale(e.id, del);
      onChanged();
    } catch (err) {
      alert((err as Error).message);
    }
  }

  return (
    <section className="card">
      <h2>Sales and Trades</h2>
      {entries.length === 0 ? (
        <p className="muted small">Nothing sold yet. Pick items above to record a sale or trade.</p>
      ) : (
        <>
          <div className="sales-filters">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search buyer, item, notes…" aria-label="Search sales" />
            <select value={via} onChange={(e) => setVia(e.target.value)} aria-label="Sold via">
              <option value="">Anywhere</option>
              {SOLD_VIA.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
              <option value="none">Not specified</option>
            </select>
            <select value={collectionId} onChange={(e) => setCollectionId(e.target.value)} aria-label="Collection">
              <option value="">All collections</option>
              {[...usedCollections].map(([k, name]) => (
                <option key={k} value={k}>
                  {name}
                </option>
              ))}
            </select>
            <label className="inline-field">
              From <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="inline-field">
              To <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </div>

          {byVia.size > 0 && (
            <div className="cards sales-totals">
              {[...byVia.values()].map((r) => (
                <div key={r.label} className="card stat">
                  <div className="stat-label">{r.label}</div>
                  <div className="stat-value">{money(dollars(r.total))}</div>
                  <div className="stat-note">
                    {r.count} item{r.count === 1 ? "" : "s"}
                    {r.hasProfit && (
                      <span className={r.profit >= 0 ? "pos" : "neg"}>
                        {" · "}
                        {r.profit >= 0 ? "+" : "−"}
                        {money(dollars(Math.abs(r.profit)))}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <ul className="sales-list">
            {shown.map((e, n) => (
              <li key={e.id ?? `one-${n}-${e.out[0]?.ref}`} className="sale-entry">
                <div className="sale-entry-head">
                  <span className={`tag ${e.kind === "trade" ? "trade" : "sold"}`}>{e.kind === "trade" ? "Trade" : "Sale"}</span>
                  <strong>{shortDate(e.sale_date)}</strong>
                  {e.sold_via && e.kind !== "trade" && <span>{soldViaLabel(e.sold_via, e.sold_via_other)}</span>}
                  {e.counterparty && (
                    <span className="muted">
                      {e.kind === "trade" ? "with" : "to"}{" "}
                      {e.dealer_id ? <Link to={`/dealers/${e.dealer_id}`}>{e.counterparty}</Link> : e.counterparty}
                    </span>
                  )}
                  <span className="sale-entry-money">
                    {money(e.total)}
                    {e.profit != null && (
                      <span className={Number(e.profit) >= 0 ? "pos" : "neg"}>
                        {" "}
                        ({Number(e.profit) >= 0 ? "+" : "−"}
                        {money(Math.abs(Number(e.profit)))})
                      </span>
                    )}
                  </span>
                  {e.id != null ? (
                    <button type="button" className="link-btn small" onClick={() => undo(e)}>
                      Undo
                    </button>
                  ) : (
                    <span className="muted small">Edit on its page</span>
                  )}
                </div>
                <div className="sale-entry-items">
                  {e.kind === "trade" && <span className="muted small">Gave</span>}
                  {e.out.map((i) => (
                    <ItemLine key={i.ref} i={i} price={i.sale_price} />
                  ))}
                  {e.kind === "trade" && (
                    <>
                      <span className="muted small">
                        Got
                        {e.cash_received ? ` (+ ${money(e.cash_received)} cash)` : ""}
                        {e.cash_paid ? ` (you added ${money(e.cash_paid)} cash)` : ""}
                      </span>
                      {e.in.map((i) => (
                        <ItemLine key={i.ref} i={i} price={i.price_paid} />
                      ))}
                    </>
                  )}
                </div>
                {e.notes && <p className="small muted">{e.notes}</p>}
              </li>
            ))}
            {shown.length === 0 && <li className="muted small">No sales match.</li>}
          </ul>
        </>
      )}
    </section>
  );
}

function ItemLine({ i, price }: { i: SaleItem; price: string | null }) {
  return (
    <div className="sale-item">
      <Link to={i.path}>{i.title}</Link> <span className="muted small">{i.inventory_number}</span>
      <span className="num small">{money(price)}</span>
    </div>
  );
}

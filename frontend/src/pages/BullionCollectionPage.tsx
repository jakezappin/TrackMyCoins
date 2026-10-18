import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type BullionCollection, type BullionItem } from "../api";
import { useApp } from "../App";
import { METAL_LABEL, ozLabel, purityLabel, quantityLabel, termLabel, weightLabel } from "../bullionFormat";
import BullionImportDialog from "../components/BullionImportDialog";
import CoinPlaceholder from "../components/CoinPlaceholder";
import ValueHistoryChart from "../components/ValueHistoryChart";
import { money, shortDate } from "../format";
import DownloadLink from "../components/DownloadLink";

const signed = (v: string | number | null | undefined) => {
  if (v == null) return "—";
  const n = Number(v);
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${money(Math.abs(n))}`;
};
const tone = (v: string | number | null | undefined) => (v == null || Number(v) === 0 ? "" : Number(v) > 0 ? "pos" : "neg");

/** A bullion collection: totals at today's spot, melt value over time, and its items. */
export default function BullionCollectionPage() {
  const { id = "" } = useParams();
  const { refresh } = useApp();
  const navigate = useNavigate();
  const [col, setCol] = useState<BullionCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const load = useCallback(() => {
    api.bullionCollection(Number(id)).then(setCol).catch((e) => setError((e as Error).message));
  }, [id]);
  useEffect(() => {
    // Another collection: don't show the previous one (or its error) while this one loads.
    setCol(null);
    setError(null);
  }, [id]);
  useEffect(load, [load]);

  async function rename() {
    if (!col) return;
    const name = prompt("Collection name", col.name)?.trim();
    if (!name || name === col.name) return;
    try {
      await api.renameBullionCollection(col.id, name);
      load();
      refresh();
    } catch (e) {
      alert(`Couldn't rename: ${(e as Error).message}`); // the page stays as it was
    }
  }

  async function remove() {
    if (!col || !confirm(`Delete ${col.name}?`)) return;
    try {
      await api.deleteBullionCollection(col.id);
      await refresh();
      navigate("/dashboard");
    } catch (e) {
      alert(`Couldn't delete: ${(e as Error).message}`);
    }
  }

  if (error) return <div className="page error">{error}</div>;
  if (!col) return <div className="page muted">Loading…</div>;
  const s = col.summary;
  const items = col.items ?? [];
  const held = items.filter((i) => !i.is_sold);
  const sold = items.filter((i) => i.is_sold);
  const spot = s.spot[col.metal];

  return (
    <div className="page bullion-page">
      <div className="page-head">
        <div>
          <h1>{col.name}</h1>
          <p className="muted">
            {METAL_LABEL[col.metal]} bullion · spot {spot ? `${money(spot)}/ozt` : "unavailable"}
          </p>
        </div>
        <div className="row">
          <button className="btn" onClick={rename}>
            Rename
          </button>
          <button className="btn" onClick={() => setImporting(true)}>
            Import
          </button>
          {items.length > 0 && (
            <DownloadLink className="btn" href={api.bullionExportUrl(col.id)}>
              Export
            </DownloadLink>
          )}
          {items.length === 0 && (
            <button className="btn danger-outline" onClick={remove}>
              Delete
            </button>
          )}
          <Link className="btn btn-primary" to={`/bullion/items/new?collection=${col.id}`}>
            + Add bullion
          </Link>
        </div>
      </div>

      <div className="coin-summary">
        <div className="card stat">
          <div className="stat-label">Current Value</div>
          <div className="stat-value">{money(s.value)}</div>
          <div className="stat-note">Melt at today's spot</div>
        </div>
        <div className="card stat">
          <div className="stat-label">Cost Basis</div>
          <div className="stat-value">{money(s.cost)}</div>
          <div className="stat-note">
            {s.count} item{s.count === 1 ? "" : "s"} on hand
            {s.sold_count > 0 && ` · realized ${signed(s.realized)}`}
          </div>
        </div>
        <div className="card stat">
          <div className="stat-label">Change</div>
          <div className={`stat-value ${tone(s.change)}`}>{signed(s.change)}</div>
          <div className="stat-note">{s.change_pct == null ? "—" : `${s.change_pct > 0 ? "+" : ""}${s.change_pct}%`}</div>
        </div>
        <div className="card stat">
          <div className="stat-label">Pure {METAL_LABEL[col.metal]}</div>
          <div className="stat-value">{ozLabel(s.oz[col.metal] ?? 0)}</div>
          <div className="stat-note">
            {s.avg_cost_oz[col.metal] ? `Avg cost ${money(s.avg_cost_oz[col.metal])}/ozt · break-even spot` : "Troy ounces"}
          </div>
        </div>
      </div>

      <ValueHistoryChart
        key={col.id}
        load={() => api.bullionCollectionHistory(col.id)}
        refreshKey={`${s.value}-${s.count}`}
        title="Melt Value Over Time"
        valueLabel="Melt value"
        emptyText="The chart fills in from the purchase date as daily spot prices are recorded."
      />

      {importing && <BullionImportDialog collectionId={col.id} onClose={() => setImporting(false)} onDone={() => { load(); refresh(); }} />}

      <BullionTable items={held} empty="Nothing here yet. Add bars, rounds, coins, rolls or tubes." />
      {sold.length > 0 && (
        <>
          <h2 className="subhead">Sold</h2>
          <BullionTable items={sold} sold />
        </>
      )}
    </div>
  );
}

function BullionTable({ items, sold = false, empty }: { items: BullionItem[]; sold?: boolean; empty?: string }) {
  const navigate = useNavigate();
  if (items.length === 0) return <div className="card muted empty">{empty}</div>;
  return (
    <div className="card table-card">
      <div className="table-scroll">
        <table className="coin-table bullion-table">
          <thead>
            <tr>
              <th className="thumb-col" />
              <th>Inv #</th>
              <th>Description</th>
              <th>Amount</th>
              <th>Purity</th>
              <th className="num">Pure</th>
              <th className="num">Paid</th>
              <th className="num">{sold ? "Sold for" : "Value"}</th>
              <th className="num">{sold ? "P/L" : "Change"}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} onClick={() => navigate(`/bullion/items/${i.inventory_number}`)}>
                <td className="thumb-col c-thumb">
                  {i.thumbnail_url ? (
                    <img src={i.thumbnail_url} alt="" className="thumb" loading="lazy" />
                  ) : (
                    <CoinPlaceholder className="thumb ph" metal={i.metal === "gold" ? "gold" : "silver"} />
                  )}
                </td>
                <td className="mono c-inv">
                  <Link to={`/bullion/items/${i.inventory_number}`} className="row-link" onClick={(e) => e.stopPropagation()}>
                    {i.inventory_number}
                  </Link>
                </td>
                <td className="strong c-date">
                  {i.description}
                  {sold && i.sale_date && <span className="sub"> {shortDate(i.sale_date)} · {termLabel(i)}</span>}
                </td>
                <td className="b-amount" data-label="Amount">
                  {weightLabel(i)}
                  {i.face_value == null && <span className="sub"> · {quantityLabel(i)}</span>}
                </td>
                <td className="b-purity" data-label="Purity">{purityLabel(i.purity)}</td>
                <td className="num b-oz" data-label="Pure">
                  {ozLabel(i.oz)}
                </td>
                <td className="num c-paid" data-label="Paid">
                  {money(i.price_paid)}
                </td>
                <td className="num b-value" data-label={sold ? "Sold for" : "Value"}>
                  {money(sold ? i.sale_price : i.value_now)}
                </td>
                <td className={`num b-change ${tone(i.change)}`} data-label={sold ? "P/L" : "Change"}>
                  {signed(i.change)}
                  {i.change_pct != null && <span className="sub"> {i.change_pct > 0 ? "+" : ""}{i.change_pct}%</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

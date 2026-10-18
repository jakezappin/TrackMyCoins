import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type BullionMeta, type BullionSummary, type Metal } from "../api";
import { useApp } from "../App";
import { METAL_LABEL, ozLabel } from "../bullionFormat";
import { money } from "../format";
import ValueHistoryChart from "./ValueHistoryChart";

/** The dashboard's bullion section: all bullion collections together, kept apart from the coin totals. */
export default function BullionDashboard() {
  const { bullionCollections } = useApp();
  const [s, setS] = useState<BullionSummary | null>(null);
  const [spot, setSpot] = useState<BullionMeta["spot"]>({});
  useEffect(() => {
    if (!bullionCollections.length) return;
    api.bullionSummary().then(setS).catch(() => setS(null));
    api.bullionMeta().then((m) => setSpot(m.spot)).catch(() => undefined);
  }, [bullionCollections]);
  if (!bullionCollections.length || !s) return null;
  const change = Number(s.change);
  const metals = Object.keys(s.by_metal ?? {}) as Metal[];
  return (
    <section className="bullion-dash">
      <div className="section-head">
        <h2>Bullion</h2>
        <span className="spot-strip small">
          {(Object.keys(METAL_LABEL) as Metal[])
            .filter((m) => spot[m])
            .map((m) => (
              <span key={m}>
                <span className="muted">{METAL_LABEL[m]}</span> <strong>{money(spot[m]!)}</strong>
              </span>
            ))}
          {spot.gold && spot.silver && (
            <span title="Ounces of silver one ounce of gold buys">
              <span className="muted">Gold/Silver</span> <strong>{(Number(spot.gold) / Number(spot.silver)).toFixed(1)}</strong>
            </span>
          )}
        </span>
      </div>
      <div className="coin-summary">
        <div className="card stat">
          <div className="stat-label">Bullion Value</div>
          <div className="stat-value">{money(s.value)}</div>
          <div className="stat-note">{s.count} item{s.count === 1 ? "" : "s"} on hand</div>
        </div>
        <div className="card stat">
          <div className="stat-label">Cost Basis</div>
          <div className="stat-value">{money(s.cost)}</div>
          <div className="stat-note">{s.sold_count ? `Realized ${money(s.realized)} on ${s.sold_count} sold` : "What you paid"}</div>
        </div>
        <div className="card stat">
          <div className="stat-label">Change</div>
          <div className={`stat-value ${change > 0 ? "pos" : change < 0 ? "neg" : ""}`}>
            {change > 0 ? "+" : change < 0 ? "−" : ""}
            {money(Math.abs(change))}
          </div>
          <div className="stat-note">{s.change_pct == null ? "—" : `${s.change_pct > 0 ? "+" : ""}${s.change_pct}%`}</div>
        </div>
        <div className="card stat">
          <div className="stat-label">Ounces</div>
          <div className="bullion-oz">
            {metals.map((m) => (
              <span key={m}>
                <strong>{ozLabel(s.oz[m])}</strong> {METAL_LABEL[m].toLowerCase()}
                {s.avg_cost_oz[m] && <span className="muted small"> · avg {money(s.avg_cost_oz[m]!)}/ozt</span>}
              </span>
            ))}
          </div>
        </div>
      </div>
      {metals.length > 1 && (
        <div className="bullion-metals">
          {bullionCollections.map((c) => (
            <Link key={c.id} to={`/bullion/${c.id}`} className="card bullion-metal">
              <span className="muted small">{c.name}</span>
              <strong>{money(c.summary.value)}</strong>
              <span className="muted small">{ozLabel(c.summary.oz[c.metal] ?? 0)}</span>
            </Link>
          ))}
        </div>
      )}
      <ValueHistoryChart load={api.bullionHistory} refreshKey={s.value} title="Bullion Value Over Time" valueLabel="Melt value"
        emptyText="The chart fills in from the purchase date as daily spot prices are recorded." />
    </section>
  );
}

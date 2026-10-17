import { useEffect, useState } from "react";
import { api, type PriceData } from "../api";
import { shortDate } from "../format";

const n = (v: number) => v.toLocaleString();

/** How much price history TrackMyCoins has collected (shared by everyone) and how big the database is. */
export default function PriceDataCard() {
  const [d, setD] = useState<PriceData | null>(null);
  useEffect(() => {
    api.priceData().then(setD).catch(() => undefined);
  }, []);
  if (!d) return null;
  const last = [d.last_sheet_update, d.last_auction_update].filter(Boolean).sort().pop();
  return (
    <section className="card form-section">
      <h2>Price History</h2>
      <p className="muted small">
        TrackMyCoins keeps the prices it looks up so it can show values over time. It updates them about once a month
        for coins people hold: CPG monthly, PCGS auction sales every 3 months.
      </p>
      <dl className="facts">
        <dt>CPG prices</dt>
        <dd>
          {n(d.cpg_prices)} across {n(d.cpg_issues)} issue{d.cpg_issues === 1 ? "" : "s"}
          {d.cpg_since && <span className="muted"> · since {shortDate(d.cpg_since)}</span>}
        </dd>
        <dt>Auction sales</dt>
        <dd>
          {n(d.auction_sales)}
          {d.auction_since && <span className="muted"> · back to {d.auction_since}</span>}
        </dd>
        <dt>PCGS guide values</dt>
        <dd>{n(d.guide_values)}</dd>
        <dt>Database size</dt>
        <dd>{d.database_mb} MB</dd>
        <dt>Last update</dt>
        <dd>{last ? shortDate(last) : "Not yet"}</dd>
      </dl>
    </section>
  );
}

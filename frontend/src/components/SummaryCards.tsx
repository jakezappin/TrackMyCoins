import type { Summary } from "../api";
import { money } from "../format";

/** "CPG $1,200 · 2 own values · 1 toner premium · 1 holder premium" plus coins still without a value. */
export function ValueNote({ summary }: { summary: Summary }) {
  const parts = [`CPG ${money(summary.total_cpg_value)}`];
  if (summary.custom_count) parts.push(`${summary.custom_count} own value${summary.custom_count === 1 ? "" : "s"}`);
  if (summary.toner_count)
    parts.push(`${summary.toner_count} toner premium${summary.toner_count === 1 ? "" : "s"} (${money(summary.toner_premium_total)})`);
  if (summary.holder_count)
    parts.push(`${summary.holder_count} holder premium${summary.holder_count === 1 ? "" : "s"} (${money(summary.holder_premium_total)})`);
  return (
    <div className="stat-note">
      {parts.join(" · ")}
      {summary.unpriced_count > 0 && (
        <span className="warn">
          {" "}
          · {summary.unpriced_count} coin{summary.unpriced_count === 1 ? "" : "s"} without a value
        </span>
      )}
    </div>
  );
}

export default function SummaryCards({ summary }: { summary: Summary }) {
  return (
    <div className="cards">
      <div className="card stat">
        <div className="stat-label">Total Price Paid</div>
        <div className="stat-value">{money(summary.total_price_paid)}</div>
        <div className="stat-note">
          {summary.coin_count} coin{summary.coin_count === 1 ? "" : "s"} on hand
        </div>
      </div>
      <div className="card stat">
        <div className="stat-label">Total Estimated Value</div>
        <div className="stat-value">{money(summary.total_estimated_value)}</div>
        <ValueNote summary={summary} />
      </div>
      <div className="card stat">
        <div className="stat-label">Est. Wholesale Value</div>
        <div className="stat-value">{money(summary.est_wholesale_value)}</div>
        <div className="stat-note">Estimated value − 10%</div>
      </div>
    </div>
  );
}

import type { Summary } from "../api";
import { money } from "../format";

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
        <div className="stat-label">Total CPG Value</div>
        <div className="stat-value">{money(summary.total_cpg_value)}</div>
        <div className={`stat-note ${summary.unpriced_count ? "warn" : ""}`}>
          {summary.unpriced_count
            ? `${summary.unpriced_count} coin${summary.unpriced_count === 1 ? "" : "s"} without a CPG price`
            : "All coins priced"}
        </div>
      </div>
      <div className="card stat">
        <div className="stat-label">Est. Wholesale Value</div>
        <div className="stat-value">{money(summary.est_wholesale_value)}</div>
        <div className="stat-note">CPG − 10%</div>
      </div>
    </div>
  );
}

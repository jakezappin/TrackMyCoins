import { useMemo, useRef, useState } from "react";
import type { AuctionSale, PcgsMarket } from "../api";
import { money, shortDate } from "../format";
import { hammerPrice } from "../premium";

interface Props {
  market: PcgsMarket | null;
  cpgValue: string | null;
  busy: boolean;
  error: string | null;
  onFetch: () => void;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
};
const monthIndex = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return y * 12 + (m - 1);
};
const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

/** Round axis bounds/ticks to friendly numbers. */
function niceTicks(lo: number, hi: number, count = 4): number[] {
  const span = Math.max(hi - lo, 1);
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s >= raw) ?? raw;
  const start = Math.floor(lo / step) * step;
  const ticks = [];
  for (let v = start; v <= hi + step * 0.001; v += step) ticks.push(Math.round(v * 100) / 100);
  if (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

// Chart geometry (SVG user units; the SVG scales to the card width).
const W = 560;
const H = 220;
const PAD = { top: 14, right: 104, bottom: 28, left: 52 };

function AuctionChart({ sales, guide, cpg }: { sales: AuctionSale[]; guide: number | null; cpg: number | null }) {
  const [hover, setHover] = useState<number | null>(null);
  const wrap = useRef<HTMLDivElement>(null);

  const pts = useMemo(() => [...sales].sort((a, b) => a.date.localeCompare(b.date)), [sales]);
  const prices = pts.map((s) => Number(s.price));
  const refs = [guide, cpg].filter((v): v is number => v != null);
  const ticks = niceTicks(Math.min(...prices, ...refs) * 0.92, Math.max(...prices, ...refs) * 1.05);
  const [yLo, yHi] = [ticks[0], ticks[ticks.length - 1]];

  const months = pts.map((s) => monthIndex(s.date));
  let [xLo, xHi] = [Math.min(...months), Math.max(...months)];
  if (xLo === xHi) [xLo, xHi] = [xLo - 1, xHi + 1];

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (m: number) => PAD.left + ((m - xLo) / (xHi - xLo)) * plotW;
  const y = (v: number) => PAD.top + (1 - (v - yLo) / (yHi - yLo)) * plotH;

  // Sales in the same month sit side by side instead of on top of each other.
  const seen = new Map<number, number>();
  const xs = pts.map((s) => {
    const m = monthIndex(s.date);
    const n = seen.get(m) ?? 0;
    seen.set(m, n + 1);
    return x(m) + (n % 2 ? 1 : -1) * Math.ceil(n / 2) * 13;
  });

  // Up to ~5 month labels on the x axis.
  const span = xHi - xLo;
  const stepMonths = Math.max(1, Math.ceil(span / 5));
  const xTicks: number[] = [];
  for (let m = xLo; m <= xHi; m += stepMonths) xTicks.push(m);

  const refLines = [
    guide != null && { value: guide, label: "PCGS Guide", dash: "6 4" },
    cpg != null && { value: cpg, label: "CPG", dash: "2 4" },
  ].filter(Boolean) as { value: number; label: string; dash: string }[];
  // Keep the two reference labels from overlapping.
  const labelY = refLines.map((r) => y(r.value));
  if (labelY.length === 2 && Math.abs(labelY[0] - labelY[1]) < 14) {
    const mid = (labelY[0] + labelY[1]) / 2;
    const [a, b] = labelY[0] <= labelY[1] ? [0, 1] : [1, 0];
    labelY[a] = mid - 7;
    labelY[b] = mid + 7;
  }

  const hovered = hover != null ? pts[hover] : null;
  const tipLeft = hover != null ? (xs[hover] / W) * 100 : 0;
  const tipTop = hover != null ? (y(Number(pts[hover].price)) / H) * 100 : 0;

  return (
    <div className="apr-chart" ref={wrap}>
      <div className="apr-plot">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Last ${pts.length} auction prices`}>
        {/* Gridlines and y axis */}
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="axis" x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
              {compact.format(t)}
            </text>
          </g>
        ))}
        {xTicks.map((m) => (
          <text key={m} className="axis" x={x(m)} y={H - 8} textAnchor="middle">
            {monthLabel(`${Math.floor(m / 12)}-${String((m % 12) + 1).padStart(2, "0")}`)}
          </text>
        ))}

        {/* Reference lines: PCGS Price Guide and CPG */}
        {refLines.map((r, i) => (
          <g key={r.label}>
            <line className="ref" x1={PAD.left} x2={W - PAD.right} y1={y(r.value)} y2={y(r.value)} strokeDasharray={r.dash} />
            <text className="ref-label" x={W - PAD.right + 8} y={labelY[i]} dy="0.32em">
              {r.label} {compact.format(r.value)}
            </text>
          </g>
        ))}

        {/* Sales */}
        {pts.map((s, i) => {
          const cx = xs[i];
          const cy = y(Number(s.price));
          const active = hover === i;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}>
              <circle cx={cx} cy={cy} r={14} className="hit" />
              {s.cac ? (
                <rect
                  className={`dot ${active ? "active" : ""}`}
                  x={cx - 5.5}
                  y={cy - 5.5}
                  width={11}
                  height={11}
                  transform={`rotate(45 ${cx} ${cy})`}
                />
              ) : (
                <circle className={`dot ${active ? "active" : ""}`} cx={cx} cy={cy} r={5.5} />
              )}
            </g>
          );
        })}
      </svg>
      {hovered && (
        <div className="apr-tip" style={{ left: `${tipLeft}%`, top: `${tipTop}%` }}>
          <strong>{money(hovered.price)}</strong>
          <span>
            {monthLabel(hovered.date)} · {hovered.auctioneer ?? "Auction"}
          </span>
          <span className="muted">
            {hovered.service}
            {hovered.cac ? " · CAC" : ""}
          </span>
        </div>
      )}
      </div>
      <div className="apr-legend small muted">
        <span>
          <svg width="12" height="12" aria-hidden>
            <circle cx="6" cy="6" r="4.5" className="dot" />
          </svg>{" "}
          Sale
        </span>
        <span>
          <svg width="12" height="12" aria-hidden>
            <rect x="2" y="2" width="8" height="8" transform="rotate(45 6 6)" className="dot" />
          </svg>{" "}
          CAC sale
        </span>
        {guide != null && <span className="legend-line dashed">PCGS Guide</span>}
        {cpg != null && <span className="legend-line dotted">CPG</span>}
      </div>
    </div>
  );
}

type PriceMode = "premium" | "hammer";
const MODE_KEY = "coinapp.auctionPriceMode";

export default function PcgsMarketCard({ market, cpgValue, busy, error, onFetch }: Props) {
  const guide = market?.price_guide != null ? Number(market.price_guide) : null;
  const cpg = cpgValue != null ? Number(cpgValue) : null;
  const [mode, setMode] = useState<PriceMode>(() => {
    try {
      return localStorage.getItem(MODE_KEY) === "hammer" ? "hammer" : "premium";
    } catch {
      return "premium";
    }
  });
  function chooseMode(m: PriceMode) {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      // not remembered; still switches
    }
  }
  // PCGS prices include the buyer's premium; "hammer" divides it back out.
  const sales = useMemo(
    () =>
      (market?.auctions ?? []).map((s) => {
        const h = hammerPrice(Number(s.price), s.auctioneer);
        return {
          ...s,
          withPremium: Number(s.price),
          hammer: h.hammer,
          rate: h.rate,
          exact: h.exact,
          price: String(mode === "hammer" ? h.hammer : Number(s.price)),
        };
      }),
    [market, mode],
  );
  const avg = sales.length ? sales.reduce((t, s) => t + Number(s.price), 0) / sales.length : null;
  const allExact = sales.every((s) => s.exact);

  return (
    <section className="card pcgs-market">
      <div className="section-head">
        <h2>PCGS market</h2>
        <button className="btn" onClick={onFetch} disabled={busy}>
          {busy ? "Fetching…" : market ? "Refresh PCGS Data" : "Get PCGS Data"}
        </button>
      </div>
      {error && <p className="error small">{error}</p>}

      {!market ? (
        <p className="muted small">
          Gets the PCGS Price Guide value, population and the last 10 auction sales for this coin's PCGS # and grade.
        </p>
      ) : (
        <>
          <p className="muted small">
            PCGS #{market.pcgs_number} · {market.grade} · as of {shortDate(market.fetched_at)}
            {market.coinfacts_url && (
              <>
                {" · "}
                <a href={market.coinfacts_url} target="_blank" rel="noreferrer">
                  CoinFacts ↗
                </a>
              </>
            )}
          </p>
          <dl className="market-stats">
            <div>
              <dt>PCGS Price Guide</dt>
              <dd>{money(market.price_guide)}</dd>
            </div>
            <div>
              <dt>
                Avg. of last {sales.length || ""} sales{mode === "hammer" ? " (hammer)" : ""}
              </dt>
              <dd>
                {mode === "hammer" && !allExact ? "≈ " : ""}
                {money(avg)}
              </dd>
            </div>
            <div>
              <dt>PCGS population</dt>
              <dd>
                {market.population?.toLocaleString() ?? "—"}
                {market.pop_higher != null && <span className="muted small"> · {market.pop_higher.toLocaleString()} higher</span>}
              </dd>
            </div>
          </dl>

          {sales.length === 0 ? (
            <p className="muted small">No recent auction sales recorded at this grade.</p>
          ) : (
            <>
              <div className="premium-toggle">
                <div className="segmented" role="tablist" aria-label="Auction prices">
                  {(
                    [
                      ["premium", "With buyer's premium"],
                      ["hammer", "Hammer (no premium)"],
                    ] as const
                  ).map(([m, label]) => (
                    <button
                      key={m}
                      type="button"
                      role="tab"
                      aria-selected={mode === m}
                      className={`seg ${mode === m ? "active" : ""}`}
                      onClick={() => chooseMode(m)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <span className="muted small">
                  {mode === "premium"
                    ? "What the buyer paid. PCGS's auction prices include the buyer's premium."
                    : "The winning bid, with each house's buyer's premium removed (e.g. Stack's 20–22%, Heritage 20%)."}
                </span>
              </div>
              <AuctionChart sales={sales} guide={guide} cpg={cpg} />
              <table className="history apr-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th className="num">{mode === "hammer" ? "Hammer" : "Price"}</th>
                    <th className="num">{mode === "hammer" ? "With premium" : "Hammer"}</th>
                    <th>Auction</th>
                    <th>Slab</th>
                  </tr>
                </thead>
                <tbody>
                  {sales.map((s, i) => (
                    <tr key={i}>
                      <td>{monthLabel(s.date)}</td>
                      <td className="num">
                        {mode === "hammer" && !s.exact ? "≈ " : ""}
                        {money(s.price)}
                      </td>
                      <td className="num muted" title={`Buyer's premium ${Math.round(s.rate * 1000) / 10}%`}>
                        {mode === "hammer" ? money(s.withPremium) : `${s.exact ? "" : "≈ "}${money(s.hammer)}`}
                        <span className="bp-rate"> ({Math.round(s.rate * 1000) / 10}%)</span>
                      </td>
                      <td>
                        {s.url ? (
                          <a href={s.url} target="_blank" rel="noreferrer" title={s.sale_name ?? undefined}>
                            {s.auctioneer ?? "Lot"}
                            {s.lot ? ` #${s.lot}` : ""} ↗
                          </a>
                        ) : (
                          s.auctioneer ?? "—"
                        )}
                      </td>
                      <td>
                        {s.service ?? ""}
                        {s.cac && <span className="tag cac-green">CAC</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </section>
  );
}

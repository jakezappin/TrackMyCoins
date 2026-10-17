import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { api, type HistoryPoint } from "../api";
import { money, shortDate } from "../format";
import CollapseHead from "./CollapseHead";
import useCollapsed from "./useCollapsed";

const H = 220;
const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

function niceMax(v: number) {
  if (v <= 0) return 100;
  const mag = 10 ** Math.floor(Math.log10(v));
  const step = [1, 1.25, 1.5, 2, 2.5, 5, 10].map((f) => f * mag).find((s) => s * 4 >= v) ?? v / 4;
  return step * 4;
}

const day = (iso: string) => new Date(iso + "T00:00:00").getTime();
/** Local YYYY-MM-DD for a timestamp (the inverse of `day`). */
const isoDay = (t: number) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Estimated value and cost over time, as step lines (values change when a price is recorded). For everything,
 * one collection, or (with `coinInv`) one coin, where cost is what was paid and the card collapses. */
export default function ValueHistoryChart({
  collectionId = null,
  coinInv,
  refreshKey,
}: {
  collectionId?: number | null;
  coinInv?: string;
  refreshKey?: unknown;
}) {
  const one = coinInv !== undefined;
  const [collapsed, toggle] = useCollapsed("collapse-coin-history", true);
  const [points, setPoints] = useState<HistoryPoint[] | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  // Draw at the real on-screen width so text stays readable on phones.
  const plotRef = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(760);
  useEffect(() => {
    const el = plotRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [points]);
  const narrow = W < 520;
  const PAD = { top: 14, right: narrow ? 62 : 110, bottom: 26, left: narrow ? 48 : 58 };

  useEffect(() => {
    (one ? api.coinHistory(coinInv) : api.history(collectionId)).then(setPoints).catch(() => setPoints([]));
  }, [collectionId, coinInv, one, refreshKey]);

  const geo = useMemo(() => {
    if (!points || points.length === 0) return null;
    const xs = points.map((p) => day(p.date));
    let [x0, x1] = [Math.min(...xs), Math.max(...xs)];
    if (x0 === x1) x0 -= 86400000 * 7;
    const top = niceMax(Math.max(...points.map((p) => Math.max(Number(p.cost), Number(p.value ?? 0)))));
    const x = (t: number) => PAD.left + ((t - x0) / (x1 - x0)) * (W - PAD.left - PAD.right);
    const y = (v: number) => PAD.top + (1 - v / top) * (H - PAD.top - PAD.bottom);
    // Step-after path: hold each value until the next date.
    const path = (get: (p: HistoryPoint) => number | null) => {
      let d = "";
      let prevY: number | null = null;
      points.forEach((p, i) => {
        const v = get(p);
        const px = x(xs[i]);
        if (v == null) {
          prevY = null;
          return;
        }
        const py = y(v);
        d += prevY == null ? `M${px},${py}` : `H${px}V${py}`;
        prevY = py;
      });
      return d;
    };
    const ticks = [0, 1, 2, 3, 4].map((i) => (top / 4) * i);
    // Date labels evenly spaced in time (not at data points, which can bunch up and overlap).
    const nTicks = narrow ? 2 : Math.max(2, Math.min(5, Math.floor((W - PAD.left - PAD.right) / 150) + 1));
    // Over a short span several ticks would show the same day: keep one label per day.
    const dateTicks = Array.from({ length: nTicks }, (_, i) => x0 + ((x1 - x0) * i) / (nTicks - 1)).filter(
      (t, i, all) => i === 0 || isoDay(t) !== isoDay(all[i - 1]),
    );
    // Value as step lines, split into recorded (solid) and backfilled (dashed) pieces.
    let solid = "";
    let dashed = "";
    points.forEach((p, i) => {
      if (p.value == null) return;
      const vy = y(Number(p.value));
      const x0 = x(xs[i]);
      const x1 = i + 1 < points.length ? x(xs[i + 1]) : x0;
      const flat = `M${x0},${vy}H${x1}`;
      if (p.backfilled) dashed += flat;
      else solid += flat;
      const next = points[i + 1];
      if (next && next.value != null) {
        const rise = `M${x1},${vy}V${y(Number(next.value))}`;
        if (next.backfilled) dashed += rise;
        else solid += rise;
      }
    });
    return { xs, x, y, ticks, dateTicks, valueSolid: solid, valueDashed: dashed, costPath: path((p) => Number(p.cost)) };
  }, [points, W]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!points) return null;
  const costWord = one ? "Paid" : "Cost";
  if (one && collapsed) {
    return (
      <section className="card history-card collapsed">
        <CollapseHead title="Value Over Time" collapsed onToggle={toggle} />
      </section>
    );
  }
  const track = (e: PointerEvent<SVGSVGElement>) => {
    if (!geo) return;
    const r = e.currentTarget.getBoundingClientRect();
    const mx = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    geo.xs.forEach((t, i) => {
      if (Math.abs(geo.x(t) - mx) < Math.abs(geo.x(geo.xs[best]) - mx)) best = i;
    });
    setHover(best);
  };
  const hasValue = points.some((p) => p.value != null);
  const anyBackfilled = points.some((p) => p.backfilled);
  const last = points[points.length - 1];

  return (
    <section className="card history-card">
      {(() => {
        const legend = (
          <div className="history-legend small">
            <span className="lg value">Estimated value</span>
            <span className="lg cost">{costWord}</span>
            {anyBackfilled && <span className="lg value dashed">Before {one ? "first price" : "prices were recorded"}</span>}
          </div>
        );
        return one ? (
          <CollapseHead title="Value Over Time" collapsed={false} onToggle={toggle}>
            {legend}
          </CollapseHead>
        ) : (
          <div className="section-head">
            <h2>Value Over Time</h2>
            {legend}
          </div>
        );
      })()}
      {!geo || points.length < 2 || !hasValue ? (
        <p className="muted small">
          {one
            ? "The chart fills in once this coin has a price. Use Get CPG Price below."
            : "The chart fills in as you add coins and record prices. Use Refresh prices to get CPG values for every coin."}
        </p>
      ) : (
        <div className="history-plot" ref={plotRef} onMouseLeave={() => setHover(null)}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label={`Estimated value ${money(last.value)} and ${costWord.toLowerCase()} ${money(last.cost)} as of ${shortDate(last.date)}`}
            onPointerMove={track}
            onPointerDown={track}
          >
            {geo.ticks.map((t) => (
              <g key={t}>
                <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={geo.y(t)} y2={geo.y(t)} />
                <text className="axis" x={PAD.left - 8} y={geo.y(t)} dy="0.32em" textAnchor="end">
                  {compact.format(t)}
                </text>
              </g>
            ))}
            {geo.dateTicks.map((t, i) => (
              <text
                key={t}
                className="axis"
                x={geo.x(t)}
                y={H - 6}
                // Keep the first and last labels inside the plot instead of hanging off the ends.
                textAnchor={i === 0 ? "start" : i === geo.dateTicks.length - 1 ? "end" : "middle"}
              >
                {shortDate(isoDay(t))}
              </text>
            ))}
            <path d={geo.costPath} className="line cost" />
            <path d={geo.valueDashed} className="line value backfilled" />
            <path d={geo.valueSolid} className="line value" />
            {/* Direct labels at the right end */}
            {last.value != null && (
              <text className="end-label" x={W - PAD.right + 8} y={geo.y(Number(last.value))} dy="0.32em">
                {compact.format(Number(last.value))}{narrow ? "" : " value"}
              </text>
            )}
            <text className="end-label" x={W - PAD.right + 8} y={geo.y(Number(last.cost)) + (last.value != null && Math.abs(geo.y(Number(last.cost)) - geo.y(Number(last.value))) < 14 ? 14 : 0)} dy="0.32em">
              {compact.format(Number(last.cost))}{narrow ? "" : ` ${costWord.toLowerCase()}`}
            </text>
            {hover != null && (
              <g>
                <line className="crosshair" x1={geo.x(geo.xs[hover])} x2={geo.x(geo.xs[hover])} y1={PAD.top} y2={H - PAD.bottom} />
                {points[hover].value != null && <circle className="dot value" cx={geo.x(geo.xs[hover])} cy={geo.y(Number(points[hover].value))} r={4.5} />}
                <circle className="dot cost" cx={geo.x(geo.xs[hover])} cy={geo.y(Number(points[hover].cost))} r={4.5} />
              </g>
            )}
          </svg>
          {hover != null && (
            <div
              className={`apr-tip history-tip ${geo.x(geo.xs[hover]) > W / 2 ? "left" : "right"}`}
              style={{ left: `${(geo.x(geo.xs[hover]) / W) * 100}%` }}
            >
              <strong>{shortDate(points[hover].date)}</strong>
              <span>
                Estimated value {money(points[hover].value)}
                {points[hover].backfilled ? " *" : ""}
              </span>
              <span>
                {costWord} {money(points[hover].cost)}
              </span>
              {points[hover].backfilled && <span className="muted">* estimated from value at purchase and auction prices</span>}
              {!one && (
                <span className="muted">
                  {points[hover].coin_count} coin{points[hover].coin_count === 1 ? "" : "s"}
                  {points[hover].priced_count < points[hover].coin_count ? `, ${points[hover].coin_count - points[hover].priced_count} without a value` : ""}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

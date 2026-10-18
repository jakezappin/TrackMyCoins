import { useEffect, useMemo, useRef, useState } from "react";

export interface LinePoint {
  date: string;
  value: number;
}

interface Props {
  points: LinePoint[];
  format: (v: number) => string;
  label: string;
  /** Optional horizontal guides, e.g. a long-run average, and a shaded normal range. */
  guides?: { value: number; label: string }[];
  band?: { low: number; high: number };
  height?: number;
}

const PAD = { top: 12, right: 12, bottom: 24, left: 56 };

function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min || Math.abs(max) || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

const shortDay = (iso: string) => {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

/** A single-series line over time with a crosshair and tooltip (spot prices, the gold/silver ratio). */
export default function LineChart({ points, format, label, guides = [], band, height = 240 }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth || 600));
    ro.observe(el);
    setWidth(el.clientWidth || 600);
    return () => ro.disconnect();
  }, []);
  useEffect(() => setHover(null), [points]);

  const geo = useMemo(() => {
    if (points.length < 2) return null;
    const values = points.map((p) => p.value).concat(guides.map((g) => g.value), band ? [band.low, band.high] : []);
    let min = Math.min(...values);
    let max = Math.max(...values);
    const padV = (max - min) * 0.06 || Math.abs(max) * 0.05 || 1;
    min -= padV;
    max += padV;
    const t0 = new Date(points[0].date).getTime();
    const t1 = new Date(points[points.length - 1].date).getTime();
    const w = Math.max(width - PAD.left - PAD.right, 10);
    const h = height - PAD.top - PAD.bottom;
    const x = (iso: string) => PAD.left + ((new Date(iso).getTime() - t0) / (t1 - t0 || 1)) * w;
    const y = (v: number) => PAD.top + (1 - (v - min) / (max - min)) * h;
    const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
    const yearSpan = (t1 - t0) / (365 * 864e5);
    const xTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const i = Math.round(f * (points.length - 1));
      const d = new Date(points[i].date + "T00:00:00");
      return {
        x: x(points[i].date),
        text: yearSpan > 2 ? String(d.getFullYear()) : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      };
    });
    return { x, y, path, yTicks: niceTicks(min, max), xTicks, w, h };
  }, [points, width, height, guides, band]);

  if (!geo) return <div className="chart-empty muted small">Not enough history to draw this yet.</div>;
  const hp = hover != null && hover < points.length ? points[hover] : null;

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left + PAD.left;
    let best = 0;
    let dist = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(geo!.x(p.date) - px);
      if (d < dist) {
        dist = d;
        best = i;
      }
    });
    setHover(best);
  }

  return (
    <div className="line-chart" ref={box}>
      <svg width={width} height={height} role="img" aria-label={label}>
        {band && (
          <rect
            x={PAD.left}
            width={geo.w}
            y={geo.y(band.high)}
            height={Math.max(geo.y(band.low) - geo.y(band.high), 0)}
            className="lc-band"
          />
        )}
        {geo.yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={PAD.left + geo.w} y1={geo.y(t)} y2={geo.y(t)} className="lc-grid" />
            <text x={PAD.left - 6} y={geo.y(t)} className="lc-axis" textAnchor="end" dominantBaseline="middle">
              {format(t)}
            </text>
          </g>
        ))}
        {geo.xTicks.map((t, i) => (
          <text key={i} x={t.x} y={height - 6} className="lc-axis" textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"}>
            {t.text}
          </text>
        ))}
        {guides.map((g) => (
          <g key={g.label}>
            <line x1={PAD.left} x2={PAD.left + geo.w} y1={geo.y(g.value)} y2={geo.y(g.value)} className="lc-guide" />
            <text x={PAD.left + geo.w - 4} y={geo.y(g.value) - 4} className="lc-axis" textAnchor="end">
              {g.label}
            </text>
          </g>
        ))}
        <path d={geo.path} className="lc-line" />
        {hp && (
          <g>
            <line x1={geo.x(hp.date)} x2={geo.x(hp.date)} y1={PAD.top} y2={PAD.top + geo.h} className="lc-cross" />
            <circle cx={geo.x(hp.date)} cy={geo.y(hp.value)} r={4} className="lc-dot" />
          </g>
        )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={geo.w}
          height={geo.h}
          fill="transparent"
          onPointerMove={onMove}
          onPointerDown={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hp && (
        <div
          className="lc-tip"
          style={{ left: Math.min(Math.max(geo.x(hp.date), 70), width - 70), top: Math.max(geo.y(hp.value) - 44, 0) }}
        >
          <strong>{format(hp.value)}</strong>
          <span>{shortDay(hp.date)}</span>
        </div>
      )}
    </div>
  );
}

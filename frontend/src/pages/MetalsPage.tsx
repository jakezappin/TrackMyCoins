import { useEffect, useMemo, useState } from "react";
import { api, type MeltRow, type MetalRange, type MetalsOverview, type PreciousMetal, type SpotCard } from "../api";
import LineChart, { type LinePoint } from "../components/LineChart";
import { money } from "../format";

const METAL_NAME: Record<PreciousMetal, string> = { gold: "Gold", silver: "Silver", platinum: "Platinum", palladium: "Palladium" };
const RANGES: [MetalRange, string][] = [["1w", "1W"], ["1m", "1M"], ["6m", "6M"], ["1y", "1Y"], ["5y", "5Y"], ["10y", "10Y"], ["all", "All"]];
const SIGNAL: Record<string, { label: string; tone: string; text: string }> = {
  trade_gold: {
    label: "Trade gold for silver",
    tone: "silver",
    text: "The ratio is above its normal range: silver is cheap next to gold. Stackers who swap between metals would trade gold for silver here.",
  },
  trade_silver: {
    label: "Trade silver for gold",
    tone: "gold",
    text: "The ratio is below its normal range: gold is cheap next to silver. Stackers who swap between metals would trade silver for gold here.",
  },
  neutral: {
    label: "Neutral",
    tone: "neutral",
    text: "The ratio is within its normal range: no strong case for swapping one metal for the other.",
  },
};

const usd = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
const pctText = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`);
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "pos" : "neg");
const arrow = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "▲ " : "▼ ");
const asOf = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null;

/** Precious metal prices, the gold/silver ratio, and what U.S. coins are worth in metal. */
export default function MetalsPage() {
  const [data, setData] = useState<MetalsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      api
        .metals()
        .then((d) => {
          if (!live) return;
          setData(d);
          setError(null);
        })
        .catch((e) => live && setError((e as Error).message));
    load();
    const t = window.setInterval(load, 5 * 60_000); // spot is cached for minutes on the server; keep the page current
    return () => {
      live = false;
      window.clearInterval(t);
    };
  }, []);

  if (error && !data) return <div className="page error">{error}</div>;
  if (!data) return <div className="page muted">Loading…</div>;
  const updated = data.spot.map((s) => s.as_of).find(Boolean) ?? null;

  return (
    <div className="page metals-page">
      <div className="page-head">
        <div>
          <h1>Precious Metals</h1>
          <p className="muted small">
            Spot prices per troy ounce{updated ? `, updated ${asOf(updated)}` : ""}. Daily change is against the previous
            day's close (markets are closed on weekends, so then it's Friday's move).
          </p>
        </div>
      </div>

      <div className="spot-cards">
        {data.spot.map((s) => (
          <SpotTile key={s.metal} s={s} />
        ))}
      </div>
      {data.copper.price != null && (
        <p className="muted small copper-line">
          Copper {usd(data.copper.price, 2)} / lb (used for copper cents below).
        </p>
      )}

      <PriceChart spot={data.spot} />
      <Performance spot={data.spot} />
      <RatioCard ratio={data.ratio} />
      <Holdings h={data.holdings} />
      <MeltCalculator rows={data.coins} junk={data.junk_oz_per_dollar} silver={data.spot.find((s) => s.metal === "silver")?.price ?? null} />
      <MeltTable rows={data.coins} />

      <p className="muted small">
        Spot prices from gold-api.com. Melt value is the metal alone at spot: dealers buy below it and sell above it, and
        collector coins are usually worth more than melt. A rule of thumb, not investment advice.
      </p>
    </div>
  );
}

function SpotTile({ s }: { s: SpotCard }) {
  return (
    <div className={`card stat spot-tile metal-${s.metal}`}>
      <div className="stat-label">{METAL_NAME[s.metal]}</div>
      <div className="stat-value">{usd(s.price)}</div>
      <div className={`stat-note ${tone(s.change)}`}>
        {s.change == null ? (
          "No previous close yet"
        ) : (
          <>
            {arrow(s.change)}
            {s.change > 0 ? "+" : s.change < 0 ? "−" : ""}
            {usd(Math.abs(s.change))} ({pctText(s.change_pct)}) {s.market_closed ? "Friday" : "today"}
          </>
        )}
      </div>
      {s.low_52w != null && s.high_52w != null && (
        <div className="stat-note muted">
          52-week {usd(s.low_52w, 0)} – {usd(s.high_52w, 0)}
        </div>
      )}
      {!s.live && <div className="stat-note muted">Live price unavailable: last close shown</div>}
    </div>
  );
}

function RangeTabs({ value, onChange }: { value: MetalRange; onChange: (r: MetalRange) => void }) {
  return (
    <div className="segmented small-seg" role="radiogroup" aria-label="Time range">
      {RANGES.map(([r, label]) => (
        <button key={r} type="button" role="radio" aria-checked={value === r} className={`seg ${value === r ? "active" : ""}`} onClick={() => onChange(r)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function useHistory(series: PreciousMetal | "ratio", range: MetalRange) {
  const [points, setPoints] = useState<LinePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setPoints(null);
    setError(null);
    api
      .metalHistory(series, range)
      .then((p) => live && setPoints(p))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [series, range]);
  return { points, error };
}

function PriceChart({ spot }: { spot: SpotCard[] }) {
  const [metal, setMetal] = useState<PreciousMetal>("gold");
  const [range, setRange] = useState<MetalRange>("1y");
  const { points, error } = useHistory(metal, range);
  const change = points && points.length > 1 ? ((points[points.length - 1].value - points[0].value) / points[0].value) * 100 : null;
  return (
    <section className="card">
      <div className="section-head wrap">
        <h2>Price History</h2>
        <div className="segmented small-seg" role="radiogroup" aria-label="Metal">
          {spot.map((s) => (
            <button key={s.metal} type="button" role="radio" aria-checked={metal === s.metal} className={`seg ${metal === s.metal ? "active" : ""}`} onClick={() => setMetal(s.metal)}>
              {METAL_NAME[s.metal]}
            </button>
          ))}
        </div>
      </div>
      <div className="row between wrap">
        <RangeTabs value={range} onChange={setRange} />
        {change != null && (
          <span className={`small ${tone(change)}`}>
            {arrow(change)}
            {pctText(change)} over this range
          </span>
        )}
      </div>
      {error ? (
        <p className="error small">{error}</p>
      ) : !points ? (
        <div className="chart-empty muted small">Loading…</div>
      ) : (
        <LineChart points={points} format={(v) => usd(v, v >= 1000 ? 0 : 2)} label={`${METAL_NAME[metal]} price, ${range}`} />
      )}
    </section>
  );
}

function Performance({ spot }: { spot: SpotCard[] }) {
  const cols: [string, (s: SpotCard) => number | null][] = [
    ["1 Day", (s) => s.change_pct],
    ["1 Week", (s) => s.changes["1w"]],
    ["1 Month", (s) => s.changes["1m"]],
    ["YTD", (s) => s.changes.ytd],
    ["1 Year", (s) => s.changes["1y"]],
  ];
  return (
    <section className="card">
      <h2>Performance</h2>
      <div className="table-scroll">
        <table className="history perf-table">
          <thead>
            <tr>
              <th>Metal</th>
              {cols.map(([h]) => (
                <th key={h} className="num">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {spot.map((s) => (
              <tr key={s.metal}>
                <td>{METAL_NAME[s.metal]}</td>
                {cols.map(([h, f]) => (
                  <td key={h} className={`num ${tone(f(s))}`}>
                    {pctText(f(s))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RatioCard({ ratio }: { ratio: MetalsOverview["ratio"] }) {
  const [range, setRange] = useState<MetalRange>("10y");
  const { points } = useHistory("ratio", range);
  const sig = ratio.signal ? SIGNAL[ratio.signal] : null;
  return (
    <section className="card">
      <div className="section-head wrap">
        <h2>Gold / Silver Ratio</h2>
        {sig && <span className={`ratio-badge ${sig.tone}`}>{sig.label}</span>}
      </div>
      <div className="ratio-head">
        <div className="big-number">{ratio.value != null ? `${ratio.value.toFixed(1)} : 1` : "—"}</div>
        <p className="small">
          An ounce of gold buys {ratio.value != null ? ratio.value.toFixed(1) : "—"} ounces of silver.
          {ratio.average != null && (
            <>
              {" "}
              Its {ratio.years}-year average is <strong>{ratio.average.toFixed(1)}</strong>, with a normal range of{" "}
              {ratio.low!.toFixed(0)}–{ratio.high!.toFixed(0)} (one standard deviation). Today is higher than{" "}
              {ratio.percentile}% of days.
            </>
          )}
        </p>
      </div>
      {sig && <p className="small muted">{sig.text}</p>}
      <RangeTabs value={range} onChange={setRange} />
      {points ? (
        <LineChart
          points={points}
          format={(v) => v.toFixed(0)}
          label={`Gold to silver ratio, ${range}`}
          guides={ratio.average != null ? [{ value: ratio.average, label: `${ratio.years}-yr avg ${ratio.average.toFixed(0)}` }] : []}
          band={ratio.low != null && ratio.high != null ? { low: ratio.low, high: ratio.high } : undefined}
        />
      ) : (
        <div className="chart-empty muted small">Loading…</div>
      )}
      <p className="muted small">Shaded: the normal range. Above it favors silver; below it favors gold.</p>
    </section>
  );
}

function Holdings({ h }: { h: MetalsOverview["holdings"] }) {
  if (!h.metals.length) return null;
  const total = h.metals.reduce((t, m) => t + (m.value ?? 0), 0);
  return (
    <section className="card">
      <div className="section-head">
        <h2>Your Metal</h2>
        <span className="big-number small-big">{money(total)}</span>
      </div>
      <div className="table-scroll">
        <table className="history">
          <thead>
            <tr>
              <th>Metal</th>
              <th className="num">Bullion</th>
              <th className="num">In coins</th>
              <th className="num">Total</th>
              <th className="num">Melt value</th>
            </tr>
          </thead>
          <tbody>
            {h.metals.map((m) => (
              <tr key={m.metal}>
                <td>{METAL_NAME[m.metal]}</td>
                <td className="num">{m.bullion_oz ? `${m.bullion_oz.toFixed(3)} ozt` : "—"}</td>
                <td className="num">{m.coin_oz ? `${m.coin_oz.toFixed(3)} ozt` : "—"}</td>
                <td className="num">{m.oz.toFixed(3)} ozt</td>
                <td className="num">{money(m.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Coins: {h.coins_counted} of your {h.coins_total} coins on hand hold precious metal (by series and date; clad and
        copper-nickel coins have none). Their collector value is usually well above melt.
      </p>
    </section>
  );
}

function MeltCalculator({ rows, junk, silver }: { rows: MeltRow[]; junk: number; silver: number | null }) {
  const [key, setKey] = useState("junk");
  const [qty, setQty] = useState("1");
  const row = rows.find((r) => r.key === key);
  const n = Number(qty);
  const valid = qty.trim() !== "" && Number.isFinite(n) && n >= 0;
  const result = !valid ? null : key === "junk" ? (silver != null ? n * junk * silver : null) : row?.melt != null ? n * row.melt : null;
  const metal = key === "junk" ? `${(n * junk).toFixed(3)} ozt silver` : row && valid ? `${(n * row.amount).toFixed(row.unit === "lb" ? 4 : 3)} ${row.unit} ${row.metal}` : "";
  return (
    <section className="card">
      <h2>Melt Calculator</h2>
      <div className="row wrap calc-row">
        <label className="field">
          <span>Coin</span>
          <select value={key} onChange={(e) => setKey(e.target.value)}>
            <option value="junk">90% junk silver (by face value)</option>
            {rows.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name} ({r.years})
              </option>
            ))}
          </select>
        </label>
        <label className="field calc-qty">
          <span>{key === "junk" ? "Face value ($)" : "Quantity"}</span>
          <input type="number" min={0} step={key === "junk" ? 0.05 : 1} value={qty} onChange={(e) => setQty(e.target.value)} />
        </label>
        <div className="field">
          <span>Melt value</span>
          <div className="big-number small-big">{result == null ? "—" : usd(result)}</div>
          <span className="muted small">{valid ? metal : "Enter a number"}</span>
        </div>
      </div>
      {key === "junk" && (
        <p className="muted small">
          $1 face of 90% dimes, quarters or halves holds {junk.toFixed(4)} oz of silver (a little less once worn; dealers
          often figure 0.715).
        </p>
      )}
    </section>
  );
}

function MeltTable({ rows }: { rows: MeltRow[] }) {
  const groups = useMemo(() => {
    const out: [string, MeltRow[]][] = [];
    for (const r of rows) {
      const g = out.find(([name]) => name === r.group);
      if (g) g[1].push(r);
      else out.push([r.group, [r]]);
    }
    return out;
  }, [rows]);
  return (
    <section className="card">
      <h2>U.S. Coin Melt Values</h2>
      <p className="muted small">What each coin's metal is worth at today's spot, and that as a multiple of its face value.</p>
      <div className="table-scroll">
        <table className="history melt-table">
          <thead>
            <tr>
              <th>Coin</th>
              <th className="hide-narrow">Years</th>
              <th className="hide-narrow">Composition</th>
              <th className="num">Metal</th>
              <th className="num">Melt</th>
              <th className="num">× Face</th>
            </tr>
          </thead>
          {groups.map(([name, list]) => (
            <tbody key={name}>
              <tr className="group-row">
                <th colSpan={6}>{name}</th>
              </tr>
              {list.map((r) => (
                <tr key={r.key}>
                  <td>
                    {r.name}
                    <span className="muted small show-narrow"> · {r.years}</span>
                  </td>
                  <td className="hide-narrow">{r.years}</td>
                  <td className="hide-narrow">{r.composition}</td>
                  <td className="num">
                    {r.unit === "lb" ? `${r.amount.toFixed(4)} lb` : `${r.amount.toFixed(r.amount >= 1 ? 2 : 4)} ozt`}
                  </td>
                  <td className="num">{r.melt == null ? "—" : usd(r.melt, r.melt < 1 ? 3 : 2)}</td>
                  <td className="num">{r.x_face == null ? "—" : `${r.x_face.toFixed(r.x_face < 10 ? 2 : 1)}×`}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <p className="muted small">
        Copper-nickel and clad coins aren't listed: there's no free nickel or zinc price to value them with, and they're
        worth about face.
      </p>
    </section>
  );
}


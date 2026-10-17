import { useEffect, useRef, useState } from "react";
import { api, type GradePrices } from "../api";
import { money, shortDate } from "../format";
import CollapseHead from "./CollapseHead";
import useCollapsed from "./useCollapsed";

/** CPG and est. wholesale for every grade of this coin's issue, with the coin's own grade highlighted. */
export default function GradePricesCard({
  inv,
  grade,
  gradePlus,
  cac,
  refreshKey,
  canFetch,
  busy,
  onFetch,
}: {
  inv: string;
  grade: number | null;
  gradePlus: boolean;
  cac: boolean;
  refreshKey: unknown;
  canFetch: boolean;
  busy: boolean;
  onFetch: () => void;
}) {
  const [collapsed, toggle] = useCollapsed("grade-prices-collapsed");
  const [data, setData] = useState<GradePrices | null>(null);
  const [showCac, setShowCac] = useState(cac);
  const mine = useRef<HTMLTableRowElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.gradePrices(inv).then(setData).catch(() => setData({ rows: null }));
  }, [inv, refreshKey]);

  // Bring the coin's own grade into view inside the scrolling table.
  useEffect(() => {
    if (collapsed || !mine.current || !scroller.current) return;
    const row = mine.current;
    scroller.current.scrollTop = row.offsetTop - scroller.current.clientHeight / 2 + row.clientHeight / 2;
  }, [collapsed, data, showCac]);

  if (!data) return null;
  const rows = data.rows;
  const isMine = (label: string, g: number) => g === grade && label.includes("+") === gradePlus;
  const cell = (v?: string) => (v ? money(v) : "—");

  return (
    <section className={`card grade-prices${collapsed ? " collapsed" : ""}`}>
      <CollapseHead title="Price by grade" collapsed={collapsed} onToggle={toggle}>
        {rows && "has_cac" in data && data.has_cac && (
          <label className="checks small">
            <span>
              <input type="checkbox" checked={showCac} onChange={(e) => setShowCac(e.target.checked)} /> CAC prices
            </span>
          </label>
        )}
      </CollapseHead>
      {collapsed ? null : !rows ? (
        <>
          <p className="muted small">
            CPG prices for every grade of this coin appear here once it has been priced (one Greysheet call gets them
            all).
          </p>
          {canFetch && (
            <div>
              <button type="button" className="btn" onClick={onFetch} disabled={busy}>
                {busy ? "Fetching…" : "Get CPG Price"}
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="grade-table" ref={scroller}>
            <table>
              <thead>
                <tr>
                  <th>Grade</th>
                  <th className="num">CPG{showCac ? " (CAC)" : ""}</th>
                  <th className="num">Est. wholesale</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const me = isMine(r.label, r.grade);
                  const cpg = showCac ? r.cac_cpg : r.cpg;
                  const ws = showCac ? r.cac_wholesale : r.wholesale;
                  return (
                    <tr key={r.label} ref={me ? mine : undefined} className={me ? "mine" : undefined}>
                      <td>
                        {r.label}
                        {me && <span className="tag">This coin</span>}
                      </td>
                      <td className="num">{cell(cpg)}</td>
                      <td className="num">{cell(ws)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            {"name" in data && data.name ? `Greysheet listing: ${data.name}. ` : ""}
            Est. wholesale is CPG − {Math.round(("wholesale_discount" in data ? data.wholesale_discount : 0.1) * 100)}%.
            {"fetched_at" in data ? ` CPG as of ${shortDate(data.fetched_at)}.` : ""}
          </p>
        </>
      )}
    </section>
  );
}

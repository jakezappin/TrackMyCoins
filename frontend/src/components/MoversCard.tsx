import { Link } from "react-router-dom";
import type { Mover } from "../api";
import { useApp } from "../App";
import { coinPath, dateMint, gradeLabel, money, shortDate } from "../format";

/** Coins whose CPG changed most at their latest price change. */
export default function MoversCard({ gainers, decliners }: { gainers: Mover[]; decliners: Mover[] }) {
  const { coinTypes } = useApp();
  if (gainers.length === 0 && decliners.length === 0) return null;
  const name = (id: number) => coinTypes.find((t) => t.id === id)?.name ?? "";

  const list = (title: string, items: Mover[], up: boolean) => (
    <div className="movers-col">
      <h3 className="small muted">{title}</h3>
      {items.length === 0 ? (
        <p className="muted small">None right now.</p>
      ) : (
        <ul>
          {items.map((m) => (
            <li key={m.coin.id}>
              <Link to={coinPath(m.coin.inventory_number)} className="mover">
                <span className="mover-name">
                  <strong>{dateMint(m.coin)}</strong> {name(m.coin.coin_type_id)} {gradeLabel(m.coin)}
                  <span className="small muted">
                    {money(m.old)} → {money(m.new)} · {shortDate(m.changed_on)}
                  </span>
                </span>
                <span className={`mover-change ${up ? "pos" : "neg"}`}>
                  {up ? "▲" : "▼"} {money(Math.abs(Number(m.change)))}
                  <span className="small">
                    {up ? "+" : "−"}
                    {Math.abs(m.pct)}%
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <section className="card movers-card">
      <div className="section-head">
        <h2>Biggest Movers</h2>
        <span className="small muted">CPG change at each coin's latest price update</span>
      </div>
      <div className="movers">
        {list("Gainers", gainers, true)}
        {list("Decliners", decliners, false)}
      </div>
    </section>
  );
}

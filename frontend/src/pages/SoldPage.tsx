import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Coin } from "../api";
import { useApp } from "../App";
import CoinTable from "../components/CoinTable";
import { money } from "../format";

export default function SoldPage() {
  const { typeSlug = "" } = useParams();
  const { coinTypes } = useApp();
  const type = coinTypes.find((t) => t.slug === typeSlug);
  const [coins, setCoins] = useState<Coin[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setCoins(null);
    setError(null);
    api
      .soldCoins(typeSlug)
      .then((c) => live && setCoins(c))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [typeSlug]);

  if (error) return <div className="page error">{error}</div>;
  if (!coins) return <div className="page muted">Loading…</div>;

  const sum = (list: Coin[], f: (c: Coin) => string | null) => list.reduce((t, c) => t + Number(f(c) ?? 0), 0);
  const sold = sum(coins, (c) => c.sale_price);
  // Profit / loss only over coins with both prices: one with no recorded cost isn't all profit.
  const both = coins.filter((c) => c.price_paid != null && c.sale_price != null);
  const paid = sum(both, (c) => c.price_paid);
  const pl = sum(both, (c) => c.sale_price) - paid;
  const left = coins.length - both.length;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{type ? `${type.plural} · Sold` : "Sold"}</h1>
      </div>
      <div className="cards">
        <div className="card stat">
          <div className="stat-label">Total Sold</div>
          <div className="stat-value">{money(sold)}</div>
          <div className="stat-note">
            {coins.length} coin{coins.length === 1 ? "" : "s"}
          </div>
        </div>
        <div className="card stat">
          <div className="stat-label">Cost of Coins Sold</div>
          <div className="stat-value">{money(paid)}</div>
          {left > 0 && <div className="stat-note">{both.length} with a recorded cost</div>}
        </div>
        <div className="card stat">
          <div className="stat-label">Profit / Loss</div>
          <div className={`stat-value ${both.length === 0 ? "" : pl >= 0 ? "pos" : "neg"}`}>{both.length ? money(pl) : "—"}</div>
          {left > 0 && (
            <div className="stat-note">
              Leaves out {left} coin{left === 1 ? "" : "s"} without a cost or sale price
            </div>
          )}
        </div>
      </div>
      <CoinTable coins={coins} mode="sold" />
    </div>
  );
}

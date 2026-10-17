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
    setCoins(null);
    api.soldCoins(typeSlug).then(setCoins).catch((e) => setError(e.message));
  }, [typeSlug]);

  if (error) return <div className="page error">{error}</div>;
  if (!coins) return <div className="page muted">Loading…</div>;

  const sum = (f: (c: Coin) => string | null) => coins.reduce((t, c) => t + Number(f(c) ?? 0), 0);
  const paid = sum((c) => c.price_paid);
  const sold = sum((c) => c.sale_price);

  return (
    <div className="page">
      <div className="page-head">
        <h1>{type?.name}s · Sold</h1>
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
        </div>
        <div className="card stat">
          <div className="stat-label">Profit / Loss</div>
          <div className={`stat-value ${sold - paid >= 0 ? "pos" : "neg"}`}>{money(sold - paid)}</div>
        </div>
      </div>
      <CoinTable coins={coins} mode="sold" />
    </div>
  );
}

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, type Coin } from "../api";
import { useApp } from "../App";
import CoinTable from "../components/CoinTable";
import { money } from "../format";

export default function SoldPage() {
  const { typeSlug = "" } = useParams();
  const { coinTypes, collections } = useApp();
  const [params, setParams] = useSearchParams();
  const pick = Number(params.get("collection")) || null;
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

  // Several collections of this series (two Morgan collections, say): one at a time, or all together.
  const all = coins;
  const mine = collections.filter((c) => c.collection_type_slug === typeSlug || all.some((x) => x.collection_id === c.id));
  const shown = pick ? all.filter((c) => c.collection_id === pick) : all;

  const sum = (list: Coin[], f: (c: Coin) => string | null) => list.reduce((t, c) => t + Number(f(c) ?? 0), 0);
  const sold = sum(shown, (c) => c.sale_price);
  // Profit / loss only over coins with both prices: one with no recorded cost isn't all profit.
  const both = shown.filter((c) => c.price_paid != null && c.sale_price != null);
  const paid = sum(both, (c) => c.price_paid);
  const pl = sum(both, (c) => c.sale_price) - paid;
  const left = shown.length - both.length;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{type ? `${type.plural} · Sold` : "Sold"}</h1>
        {mine.length > 1 && (
          <label className="field sold-filter">
            <span>Collection</span>
            <select
              value={pick ?? ""}
              onChange={(e) => setParams(e.target.value ? { collection: e.target.value } : {}, { replace: true })}
            >
              <option value="">All collections ({all.length})</option>
              {mine.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({all.filter((x) => x.collection_id === c.id).length})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="cards">
        <div className="card stat">
          <div className="stat-label">Total Sold</div>
          <div className="stat-value">{money(sold)}</div>
          <div className="stat-note">
            {shown.length} coin{shown.length === 1 ? "" : "s"}
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
      <CoinTable coins={shown} mode="sold" />
    </div>
  );
}

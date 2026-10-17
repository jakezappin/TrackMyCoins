import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type DashboardData } from "../api";
import { useApp } from "../App";
import CoinPlaceholder from "../components/CoinPlaceholder";
import HScroll from "../components/HScroll";
import NewCollectionDialog from "../components/NewCollectionDialog";
import QuickSearch from "../components/QuickSearch";
import ValueHistoryChart from "../components/ValueHistoryChart";
import MoreMenu from "../components/MoreMenu";
import MoversCard from "../components/MoversCard";
import { NGC_BOOKMARK_ENABLED } from "../ngcButton";
import RefreshPrices, { RefreshSlot } from "../components/RefreshPrices";
import { ValueNote } from "../components/SummaryCards";
import { coinPath, collectionPath, dateMint, FINISH_LABEL, gradeLabel, metalFor, money, shortDate, soldPath } from "../format";

function timeAgo(iso: string | null): string {
  if (!iso) return "Not opened yet";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "Opened just now";
  if (mins < 60) return `Opened ${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `Opened ${hrs} hr${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `Opened ${days} day${days === 1 ? "" : "s"} ago`;
  return `Opened ${shortDate(iso)}`;
}

export default function DashboardPage() {
  const { user, collections, coinTypes } = useApp();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  // Refetch when collections change (e.g. one was created or a coin's totals changed).
  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setError(e.message));
  }, [collections]);
  const { refresh } = useApp();

  if (error) return <div className="page error">{error}</div>;
  if (!data) return <div className="page muted">Loading…</div>;

  const t = data.totals;
  const typeName = (id: number) => coinTypes.find((x) => x.id === id)?.name ?? "";

  return (
    <div className="page dashboard">
      <div className="page-head">
        <div>
          <h1>Welcome, {user?.first_name}</h1>
          <p className="muted">
            {t.coin_count} coin{t.coin_count === 1 ? "" : "s"} in {t.collection_count} collection
            {t.collection_count === 1 ? "" : "s"}
          </p>
        </div>
        <div className="head-actions">
          <span className="act-refresh">
            <RefreshPrices collectionId={null} coinCount={t.coin_count} onDone={refresh} />
          </span>
          <span className="act-more">
            <MoreMenu>
              <Link to="/import">Import coins</Link>
              {NGC_BOOKMARK_ENABLED && <Link to="/ngc-button">NGC one-tap button</Link>}
              <a href={api.insuranceUrl(null)} download>
                Insurance report (PDF)
              </a>
            </MoreMenu>
          </span>
          <button className="btn btn-primary act-add" onClick={() => setCreating(true)}>
            + New collection
          </button>
        </div>
      </div>

      <RefreshSlot />
      <QuickSearch />

      {/* Row 1: totals across every collection */}
      <div className="cards">
        <div className="card stat">
          <div className="stat-label">Total Collection Cost</div>
          <div className="stat-value">{money(t.total_price_paid)}</div>
          <div className="stat-note">
            {t.coin_count} coin{t.coin_count === 1 ? "" : "s"} on hand
          </div>
        </div>
        <div className="card stat">
          <div className="stat-label">Total Collection Estimated Value</div>
          <div className="stat-value">{money(t.total_estimated_value)}</div>
          <ValueNote summary={t} />
        </div>
        <div className="card stat">
          <div className="stat-label">Total Collection Wholesale Value</div>
          <div className="stat-value">{money(t.est_wholesale_value)}</div>
          <div className="stat-note">Estimated value − 10%</div>
        </div>
      </div>

      <ValueHistoryChart collectionId={null} refreshKey={data.totals} />
      <MoversCard gainers={data.gainers} decliners={data.decliners} />

      {/* Row 2: recently opened collections */}
      <section className="section">
        <div className="section-head">
          <h2>Recent Collections</h2>
        </div>
        {data.recent_collections.length === 0 ? (
          <div className="card empty-state">
            <p>You don't have any collections yet.</p>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              Create your first collection
            </button>
          </div>
        ) : (
          <HScroll label="Recent collections">
            {data.recent_collections.map((c) => (
              <Link key={c.id} to={collectionPath(c)} className="card collection-tile hcard">
                <h3>
                  {c.name}
                  {c.finish !== "MS" && <span className="tag finish">{FINISH_LABEL[c.finish]}</span>}
                </h3>
                <div className="muted small">{c.collection_type_label}</div>
                <dl className="mini-stats">
                  <div>
                    <dt>Paid</dt>
                    <dd>{money(c.summary.total_price_paid)}</dd>
                  </div>
                  <div>
                    <dt>Value</dt>
                    <dd>{money(c.summary.total_estimated_value)}</dd>
                  </div>
                  <div>
                    <dt>Wholesale</dt>
                    <dd>{money(c.summary.est_wholesale_value)}</dd>
                  </div>
                </dl>
                <div className="hcard-foot muted small">
                  <span>
                    {c.summary.coin_count} coin{c.summary.coin_count === 1 ? "" : "s"}
                  </span>
                  <span>{timeAgo(c.last_viewed_at)}</span>
                </div>
              </Link>
            ))}
          </HScroll>
        )}
      </section>

      {/* Row 3: recent sales */}
      <section className="section">
        <div className="section-head">
          <h2>Recent Sales</h2>
        </div>
        {data.recent_sales.length === 0 ? (
          <div className="card empty-state">
            <p className="muted">
              No sales yet. Fill in a sale price and date on a coin and it shows up here and on its series' Sold list.
            </p>
          </div>
        ) : (
          <HScroll label="Recent sales">
            {data.recent_sales.map(({ coin, collection_name, profit }) => {
              const pl = profit == null ? null : Number(profit);
              return (
                <Link key={coin.id} to={coinPath(coin.inventory_number)} className="card hcard sale-card">
                  <div className="sale-top">
                    {coin.thumbnail_url ? (
                      <img src={coin.thumbnail_url} alt="" className="sale-thumb" />
                    ) : (
                      <CoinPlaceholder className="sale-thumb ph" metal={metalFor(coinTypes, coin.coin_type_id)} />
                    )}
                    <div className="sale-title">
                      <strong>
                        {dateMint(coin)} {typeName(coin.coin_type_id)}
                      </strong>
                      <span className="muted small">
                        {gradeLabel(coin)} · {coin.inventory_number}
                      </span>
                    </div>
                  </div>
                  <div className="sale-money">
                    <div>
                      <span className="stat-label">Sold for</span>
                      <strong className="sale-price">{money(coin.sale_price)}</strong>
                    </div>
                    <div className="sale-pl">
                      <span className="stat-label">Profit / loss</span>
                      <strong className={pl == null ? "" : pl >= 0 ? "pos" : "neg"}>
                        {pl == null ? "—" : `${pl >= 0 ? "+" : "−"}${money(Math.abs(pl))}`}
                      </strong>
                    </div>
                  </div>
                  <div className="hcard-foot muted small">
                    <span>{coin.sale_date ? shortDate(coin.sale_date) : "No sale date"}</span>
                    <span className="truncate">{coin.sold_to ? `to ${coin.sold_to}` : collection_name}</span>
                  </div>
                </Link>
              );
            })}
          </HScroll>
        )}
        {data.recent_sales.length > 0 && (
          <div className="row small">
            <span className="muted">All sales by series:</span>
            {[...new Set(data.recent_sales.map((s) => s.coin.coin_type_slug))].map((slug) => {
              const ct = coinTypes.find((x) => x.slug === slug);
              return (
                <Link key={slug} to={soldPath(slug)}>
                  {ct?.plural ?? slug}
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {creating && (
        <NewCollectionDialog onClose={() => setCreating(false)} onCreated={(c) => navigate(collectionPath(c))} />
      )}
    </div>
  );
}

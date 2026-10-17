import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Coin, type Collection } from "../api";
import { useApp } from "../App";
import CoinTable from "../components/CoinTable";
import ShareCollection from "../components/ShareCollection";
import MoreMenu from "../components/MoreMenu";
import RefreshPrices, { RefreshSlot } from "../components/RefreshPrices";
import SummaryCards from "../components/SummaryCards";
import ValueHistoryChart from "../components/ValueHistoryChart";
import { collectionPath } from "../format";

export default function CollectionPage() {
  const { typeSlug = "", number } = useParams();
  const { refresh } = useApp();
  const navigate = useNavigate();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [coins, setCoins] = useState<Coin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");

  const load = useCallback(() => {
    return api
      .collectionByNumber(typeSlug, Number(number))
      .then(async (c) => {
        setCollection(c);
        setName(c.name);
        setCoins(await api.collectionCoins(c.id));
      })
      .catch((e) => setError(e.message));
  }, [typeSlug, number]);

  useEffect(() => {
    setCollection(null);
    setCoins(null);
    setError(null);
    load();
  }, [load]);

  // After a price refresh: reload this page's totals and the sidebar/dashboard data.
  const reload = useCallback(() => {
    load();
    refresh();
  }, [load, refresh]);

  async function saveName(e: React.FormEvent) {
    e.preventDefault();
    try {
      setCollection(await api.renameCollection(collection!.id, name));
      setRenaming(false);
      refresh();
    } catch (err) {
      alert((err as Error).message);
    }
  }

  async function remove() {
    if (!confirm(`Delete the collection "${collection?.name}"? This only works if it has no coins.`)) return;
    try {
      await api.deleteCollection(collection!.id);
      await refresh();
      navigate("/dashboard");
    } catch (err) {
      alert((err as Error).message);
    }
  }

  if (error) return <div className="page error">{error}</div>;
  if (!collection || !coins) return <div className="page muted">Loading…</div>;

  return (
    <div className="page">
      <div className="page-head">
        {renaming ? (
          <form className="row" onSubmit={saveName}>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus className="title-input" />
            <button className="btn btn-primary">Save</button>
            <button type="button" className="btn" onClick={() => setRenaming(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <div>
            <h1>{collection.name}</h1>
            <p className="muted">{collection.collection_type_label}</p>
          </div>
        )}
        <div className="head-actions">
          <span className="act-refresh">
            <RefreshPrices collectionId={collection.id} coinCount={collection.summary.coin_count} onDone={reload} />
          </span>
          <Link className="btn act-status" to={`${collectionPath(collection)}/status`}>
            Collection Status
          </Link>
          <span className="act-more">
            <MoreMenu>
              <Link to={`/import?collection=${collection.id}`}>Import coins</Link>
              <a href={api.exportUrl(collection.id)} download>
                Export to Excel
              </a>
              <a href={api.insuranceUrl(collection.id)} download>
                Insurance report (PDF)
              </a>
              <ShareCollection collection={collection} onChange={setCollection} asMenuItem />
              <hr />
              <button type="button" onClick={() => setRenaming(true)}>Rename collection</button>
              <button type="button" className="danger" onClick={remove}>
                Delete collection
              </button>
            </MoreMenu>
          </span>
          <Link className="btn btn-primary act-add" to={`/coins/new?collection=${collection.id}`}>
            + Add coin
          </Link>
        </div>
      </div>

      <RefreshSlot />
      <SummaryCards summary={collection.summary} />
      <ValueHistoryChart collectionId={collection.id} refreshKey={collection.summary} />
      <CoinTable coins={coins} mode="collection" />
    </div>
  );
}

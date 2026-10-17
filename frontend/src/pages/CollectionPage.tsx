import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Coin, type Collection } from "../api";
import { useApp } from "../App";
import CoinTable from "../components/CoinTable";
import SummaryCards from "../components/SummaryCards";
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

  useEffect(() => {
    setCollection(null);
    setCoins(null);
    setError(null);
    api
      .collectionByNumber(typeSlug, Number(number))
      .then(async (c) => {
        setCollection(c);
        setName(c.name);
        setCoins(await api.collectionCoins(c.id));
      })
      .catch((e) => setError(e.message));
  }, [typeSlug, number]);

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
      navigate("/");
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
        <div className="row">
          <details className="menu">
            <summary className="btn">⋯</summary>
            <div className="menu-pop">
              <button onClick={() => setRenaming(true)}>Rename collection</button>
              <button className="danger" onClick={remove}>
                Delete collection
              </button>
            </div>
          </details>
          <Link className="btn" to={`${collectionPath(collection)}/status`}>
            Collection Status
          </Link>
          <a className="btn" href={api.exportUrl(collection.id)} download>
            Export
          </a>
          <Link className="btn btn-primary" to={`/coins/new?collection=${collection.id}`}>
            + Add coin
          </Link>
        </div>
      </div>

      <SummaryCards summary={collection.summary} />
      <CoinTable coins={coins} mode="collection" />
    </div>
  );
}

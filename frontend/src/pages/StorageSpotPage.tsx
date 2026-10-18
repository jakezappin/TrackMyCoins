import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, downloadFile, type StorageSpot, type StoredItem } from "../api";
import { coinPath, money } from "../format";
import { SpotDialog } from "./StoragePage";

type Hit = { kind: "coin" | "bullion"; inventory_number: string; label: string; storedHere: boolean; sold: boolean };

/** One storage spot: what's in it (in position order), adding and removing items, and printouts. */
export default function StorageSpotPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [spot, setSpot] = useState<StorageSpot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [printing, setPrinting] = useState<string | null>(null);

  const load = () =>
    api
      .storageSpot(Number(id))
      .then(setSpot)
      .catch((e) => setError((e as Error).message));
  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !spot) return <div className="page error">{error}</div>;
  if (!spot) return <div className="page muted">Loading…</div>;
  const n = spot.items.length;

  async function print(values: boolean) {
    setPrinting(values ? "values" : "checklist");
    try {
      await downloadFile(api.storageReportUrl(spot!.id, values));
    } catch (e) {
      alert(`Couldn't make the printout: ${(e as Error).message}`);
    } finally {
      setPrinting(null);
    }
  }

  async function remove() {
    const what = n === 0 ? "" : n === 1 ? " The item in it stays in your collection, just not stored anywhere." : ` The ${n} items in it stay in your collections, just not stored anywhere.`;
    if (!confirm(`Delete ${spot!.name}?${what}`)) return;
    try {
      await api.deleteStorageSpot(spot!.id);
      navigate("/storage");
    } catch (e) {
      alert(`Couldn't delete: ${(e as Error).message}`);
    }
  }

  return (
    <div className="page storage-spot-page">
      <Link to="/storage" className="btn small back-link">
        ← Storage
      </Link>
      <div className="page-head">
        <div>
          <h1>{spot.name}</h1>
          <p className="muted small">
            {n} item{n === 1 ? "" : "s"} · {money(spot.value)}
            {spot.notes ? ` · ${spot.notes}` : ""}
          </p>
        </div>
        <div className="row wrap">
          <button className="btn" onClick={() => print(true)} disabled={printing !== null || n === 0}>
            {printing === "values" ? "Preparing…" : "Print with values"}
          </button>
          <button className="btn" onClick={() => print(false)} disabled={printing !== null || n === 0}>
            {printing === "checklist" ? "Preparing…" : "Print checklist"}
          </button>
          <button className="btn" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button className="btn danger" onClick={remove}>
            Delete
          </button>
        </div>
      </div>

      <section className="card">
        <h2>What's Here</h2>
        <AddItem spot={spot} onChange={setSpot} />
        {n === 0 ? (
          <p className="muted small">Nothing yet. Search above to add coins or bullion.</p>
        ) : (
          <div className="table-scroll">
            <table className="history storage-items">
              <thead>
                <tr>
                  <th>Position</th>
                  <th>Item</th>
                  <th>Grade / details</th>
                  <th className="num">Value</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {spot.items.map((it) => (
                  <ItemRow key={`${it.kind}-${it.inventory_number}`} spot={spot} it={it} onChange={setSpot} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {editing && <SpotDialog spot={spot} onClose={() => setEditing(false)} onSaved={load} />}
    </div>
  );
}

function ItemRow({ spot, it, onChange }: { spot: StorageSpot; it: StoredItem; onChange: (s: StorageSpot) => void }) {
  const [position, setPosition] = useState(it.position ?? "");
  useEffect(() => setPosition(it.position ?? ""), [it.position]);
  const href = it.kind === "coin" ? coinPath(it.inventory_number) : `/bullion/items/${it.inventory_number}`;

  async function save() {
    if (position === (it.position ?? "")) return;
    try {
      onChange(await api.storeItem(spot.id, { kind: it.kind, inventory_number: it.inventory_number, position: position || null }));
    } catch (e) {
      alert((e as Error).message);
    }
  }

  return (
    <tr>
      <td>
        <input
          className="cell-input"
          value={position}
          onChange={(e) => setPosition(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          placeholder="e.g. Page 3, hole 14"
          maxLength={60}
          aria-label={`Position of ${it.inventory_number}`}
        />
      </td>
      <td>
        <Link to={href}>{it.title}</Link>
        <div className="muted small">
          {it.inventory_number}
          {it.subtitle ? ` · ${it.subtitle}` : ""}
          {it.at_grading && <span className="tag grading">At grading</span>}
        </div>
      </td>
      <td className="small">{it.grade}</td>
      <td className="num">{money(it.value)}</td>
      <td>
        <button
          type="button"
          className="link-btn small icon-x"
          aria-label={`Take ${it.inventory_number} out of ${spot.name}`}
          onClick={async () => {
            if (!confirm(`Take ${it.inventory_number} out of ${spot.name}?`)) return;
            try {
              onChange(await api.unstoreItem(spot.id, it.kind, it.inventory_number));
            } catch (e) {
              alert((e as Error).message);
            }
          }}
        >
          ✕
        </button>
      </td>
    </tr>
  );
}

function AddItem({ spot, onChange }: { spot: StorageSpot; onChange: (s: StorageSpot) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (!term) return setHits([]);
    let live = true;
    const here = new Set(spot.items.map((i) => `${i.kind}-${i.inventory_number}`));
    const t = window.setTimeout(() => {
      Promise.all([api.searchCoins(term, 8), api.searchBullion(term).catch(() => [])])
        .then(([coins, bullion]) => {
          if (!live) return;
          setHits([
            ...coins.map((h) => ({
              kind: "coin" as const,
              inventory_number: h.coin.inventory_number,
              label: `${h.coin.year}${h.coin.mint_mark !== "P" ? `-${h.coin.mint_mark}` : ""} ${h.type_name} · ${h.collection_name}${
                h.coin.storage_name && h.coin.storage_id !== spot.id ? ` · now in ${h.coin.storage_name}` : ""
              }`,
              storedHere: here.has(`coin-${h.coin.inventory_number}`),
              sold: h.coin.is_sold,
            })),
            ...bullion.map((b) => ({
              kind: "bullion" as const,
              inventory_number: b.inventory_number,
              label: `${b.description} · ${b.collection_name}`,
              storedHere: here.has(`bullion-${b.inventory_number}`),
              sold: b.is_sold,
            })),
          ]);
        })
        .catch(() => live && setHits([]));
    }, 150);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [q, spot]);

  return (
    <div className="coin-search">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Add an item: inventory #, cert, 1881-S, Morgan, Buffalo round…"
        aria-label="Search your coins and bullion to add"
        maxLength={100}
      />
      {hits.length > 0 && (
        <ul className="coin-search-hits">
          {hits.map((h) => (
            <li key={`${h.kind}-${h.inventory_number}`}>
              <span>
                <strong>{h.inventory_number}</strong> {h.label}
              </span>
              <button
                type="button"
                className="btn small"
                disabled={h.storedHere || h.sold}
                onClick={async () => {
                  setError(null);
                  try {
                    onChange(await api.storeItem(spot.id, { kind: h.kind, inventory_number: h.inventory_number }));
                    setQ("");
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                {h.storedHere ? "Here" : h.sold ? "Sold" : "+ Add"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

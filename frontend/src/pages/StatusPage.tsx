import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Coin, type Collection, type CollectionStatus, type StatusMode } from "../api";
import { coinPath, collectionPath, dateMint, serviceLabel, gradeLabel, money, toningLabel } from "../format";

type Filter = "all" | "missing" | "owned";

// Remember full set vs type set per collection (in this browser only).
const modeKey = (collectionId: number) => `coinapp.statusMode.${collectionId}`;
function savedMode(collectionId: number): StatusMode {
  try {
    return localStorage.getItem(modeKey(collectionId)) === "type" ? "type" : "full";
  } catch {
    return "full";
  }
}

function CoinChip({ coin }: { coin: Coin }) {
  return (
    <Link to={coinPath(coin.inventory_number)} className="status-coin" title={coin.inventory_number}>
      <span className="status-grade">{gradeLabel(coin)}</span>
      <span className="muted small">{serviceLabel(coin.grading_service)}</span>
      {coin.cac && <span className={`tag cac-${coin.cac_sticker ?? "green"}`}>CAC</span>}
      {toningLabel(coin).length > 0 && <span className="tag toned">Toned</span>}
      {coin.latest_cpg?.value && <span className="muted small">{money(coin.latest_cpg.value)}</span>}
    </Link>
  );
}

export default function StatusPage() {
  const { typeSlug = "", number } = useParams();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [status, setStatus] = useState<CollectionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [mode, setMode] = useState<StatusMode | null>(null);

  useEffect(() => {
    setCollection(null);
    setStatus(null);
    setError(null);
    setMode(null);
    api
      .collectionByNumber(typeSlug, Number(number))
      .then((c) => {
        setCollection(c);
        setMode(savedMode(c.id));
      })
      .catch((e) => setError(e.message));
  }, [typeSlug, number]);

  useEffect(() => {
    if (!collection || !mode) return;
    let cancelled = false;
    api
      .collectionStatus(collection.id, mode)
      .then((s) => !cancelled && setStatus(s))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [collection, mode]);

  function chooseMode(m: StatusMode) {
    if (!collection || m === mode) return;
    try {
      localStorage.setItem(modeKey(collection.id), m);
    } catch {
      // not saved; still switch for this visit
    }
    setStatus(null);
    setMode(m);
  }

  const rows = useMemo(() => {
    if (!status) return [];
    if (filter === "missing") return status.rows.filter((r) => r.coins.length === 0);
    if (filter === "owned") return status.rows.filter((r) => r.coins.length > 0);
    return status.rows;
  }, [status, filter]);

  if (error) return <div className="page error">{error}</div>;
  if (!collection || !status)
    return <div className="page muted">Loading the checklist… (the first time for a series can take a few seconds)</div>;

  const pct = status.total ? Math.round((status.filled / status.total) * 100) : 0;
  const unit = status.mode === "type" ? "designs" : "dates";
  // One date-column width for the whole list, sized to the longest label (e.g. commemorative names).
  const longest = Math.max(0, ...status.rows.map((r) => r.label.length));
  const listStyle = { "--date-col": `${Math.min(320, Math.max(150, longest * 8 + 16))}px` } as React.CSSProperties;
  const missing = status.total - status.filled;

  return (
    <div className="page">
      <div>
        <Link className="btn back-btn" to={collectionPath(collection)}>
          ← Back to {collection.name}
        </Link>
      </div>
      <div className="page-head">
        <div>
          <h1>Collection Status</h1>
          <p className="muted">
            {collection.name} · {collection.collection_type_label}
          </p>
        </div>
        <a className="btn" href={api.exportUrl(collection.id)} download>
          Export
        </a>
      </div>

      {status.modes.length > 1 && (
        <div className="segmented mode-switch" role="tablist" aria-label="Checklist">
          {(
            [
              ["full", "Full set", "Every date, mint and issue"],
              ["type", "Type set", "One coin per design"],
            ] as const
          ).map(([m, label, hint]) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={status.mode === m}
              className={`seg ${status.mode === m ? "active" : ""}`}
              onClick={() => chooseMode(m)}
              title={hint}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <div className="card progress-card">
        <div className="progress-text">
          <strong>
            {status.filled} of {status.total}
          </strong>{" "}
          {unit} filled <span className="muted">· {missing} missing</span>
          <span className="progress-pct">{pct}%</span>
        </div>
        <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-bar" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="card table-card">
        <div className="table-toolbar">
          <div className="chips">
            {(
              [
                ["all", `All (${status.total})`],
                ["missing", `Show missing (${missing})`],
                ["owned", `Owned (${status.filled})`],
              ] as const
            ).map(([f, label]) => (
              <button key={f} className={`chip ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>
                {label}
              </button>
            ))}
          </div>
        </div>
        {rows.length === 0 ? (
          <p className="muted empty">{filter === "missing" ? "Nothing missing. The set is complete! 🎉" : "Nothing here yet."}</p>
        ) : (
          <ul className="status-list" style={listStyle}>
            {rows.map((r) => (
              <li key={r.label} className={`status-row ${r.coins.length ? "have" : "missing"}`}>
                <span className="status-mark" aria-label={r.coins.length ? "Owned" : "Missing"}>
                  {r.coins.length ? "✓" : ""}
                </span>
                <span className="status-date">{r.label}</span>
                <span className="status-coins">
                  {r.coins.length ? (
                    r.coins.map((c) => <CoinChip key={c.id} coin={c} />)
                  ) : (
                    <span className="tag missing-tag">Missing</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {status.others.length > 0 && (
        <div className="card">
          <h2>Other coins in this collection</h2>
          <p className="muted small">
            These don't match a date in the catalog for this series. Check the year and mint. For commemoratives
            and Washington quarters from 1999 on, set the Variety / issue (e.g. "Delaware") or the PCGS #.
          </p>
          <ul className="status-list">
            {status.others.map((c) => (
              <li key={c.id} className="status-row have">
                <span className="status-mark" />
                <span className="status-date">{dateMint(c)}</span>
                <span className="status-coins">
                  <CoinChip coin={c} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type SharedCoin, type SharedCollection } from "../api";
import CoinPlaceholder from "../components/CoinPlaceholder";
import Logo from "../components/Logo";
import { dateMint, gradeLabel, money, serviceLabel, slabLabel, toningLabel } from "../format";

/** Public, read-only view of a shared collection (no login). */
export default function SharedCollectionPage() {
  const { token = "" } = useParams();
  const [data, setData] = useState<SharedCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<SharedCoin | null>(null);

  useEffect(() => {
    api
      .shared(token)
      .then((d) => {
        setData(d);
        document.title = `${d.name} · TrackMyCoins`;
      })
      .catch((e) => setError((e as Error).message));
  }, [token]);

  return (
    <div className="shared">
      <header className="shared-bar">
        <Link to="/" aria-label="TrackMyCoins home">
          <Logo size={28} />
        </Link>
        <span className="muted small">Shared collection · view only</span>
      </header>

      <main className="shared-main">
        {error && (
          <div className="card empty-state">
            <h2>Link Not Available</h2>
            <p className="muted">{error}</p>
          </div>
        )}
        {!data && !error && <p className="muted">Loading…</p>}
        {data && (
          <>
            <div className="shared-head">
              <div>
                <p className="muted small shared-eyebrow">{data.collection_type_label}</p>
                <h1>{data.name}</h1>
                <p className="muted">
                  {data.owner}'s collection · {data.coin_count} coin{data.coin_count === 1 ? "" : "s"}
                </p>
              </div>
              {data.show_values && (
                <div className="card stat">
                  <div className="stat-label">Estimated value</div>
                  <div className="stat-value">{money(data.total_estimated_value)}</div>
                </div>
              )}
            </div>

            {data.coins.length === 0 ? (
              <p className="muted">No coins in this collection yet.</p>
            ) : (
              <div className="shared-grid">
                {data.coins.map((c) => (
                  <button key={c.id} className="card shared-coin" onClick={() => setOpen(c)}>
                    {c.photo_urls[0] ? (
                      <img src={c.thumb_url ?? c.photo_urls[0]} alt={`${dateMint(c)} ${data.coin_type_name}`} loading="lazy" />
                    ) : (
                      <CoinPlaceholder date={dateMint(c)} typeName={data.coin_type_name} metal={data.metal} note="" />
                    )}
                    <div className="shared-coin-body">
                      <strong>{dateMint(c)}</strong>
                      <span>
                        {serviceLabel(c.grading_service)} {gradeLabel(c).replace(/^Raw ?/, "")}
                      </span>
                      <CoinTags c={c} />
                      {data.show_values && c.value_estimate && <span className="muted small">{money(c.value_estimate)}</span>}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </main>

      {open && data && <CoinModal c={open} typeName={data.coin_type_name} showValue={data.show_values} onClose={() => setOpen(null)} />}

      <footer className="shared-foot muted small">
        Organized with <Link to="/">TrackMyCoins</Link>
      </footer>
    </div>
  );
}

function CoinTags({ c }: { c: SharedCoin }) {
  const toning = toningLabel(c);
  const slabs = slabLabel(c);
  if (!c.cac && !toning.length && !slabs.length) return null;
  return (
    <div className="tags">
      {c.cac && <span className={`tag cac-${c.cac_sticker ?? "green"}`}>CAC</span>}
      {toning.length > 0 && <span className="tag toned">Toned</span>}
      {slabs.map((s) => (
        <span key={s} className="tag slab">
          {s}
        </span>
      ))}
    </div>
  );
}

function CoinModal({ c, typeName, showValue, onClose }: { c: SharedCoin; typeName: string; showValue: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const toning = toningLabel(c);
  const slabs = slabLabel(c);
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="modal shared-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()} aria-label={`${dateMint(c)} ${typeName}`}>
        <div className="row-end">
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {c.photo_urls.length > 0 && (
          <>
            <img className="shared-photo" src={c.photo_urls[i]} alt={`${dateMint(c)} ${typeName}, photo ${i + 1}`} />
            {c.photo_urls.length > 1 && (
              <div className="thumb-row">
                {c.photo_urls.map((u, j) => (
                  <button key={u} className={`thumb-btn${j === i ? " active" : ""}`} onClick={() => setI(j)} aria-label={`Photo ${j + 1}`}>
                    <img src={u} alt="" />
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        <h2>
          {dateMint(c)} {typeName}
        </h2>
        <dl className="facts">
          <dt>Grade</dt>
          <dd>{gradeLabel(c)}</dd>
          <dt>Graded by</dt>
          <dd>{c.grading_service === "RAW" ? "Ungraded" : `${c.grading_service}${c.cert_number ? ` #${c.cert_number}` : ""}`}</dd>
          {c.cac && (
            <>
              <dt>CAC</dt>
              <dd style={{ textTransform: "capitalize" }}>{c.cac_sticker ?? "Yes"}</dd>
            </>
          )}
          {c.variety && (
            <>
              <dt>Variety</dt>
              <dd>{c.variety}</dd>
            </>
          )}
          {c.vam && (
            <>
              <dt>VAM</dt>
              <dd>{c.vam}</dd>
            </>
          )}
          {slabs.length > 0 && (
            <>
              <dt>Holder</dt>
              <dd>{slabs.join(", ")}</dd>
            </>
          )}
          {toning.length > 0 && (
            <>
              <dt>Toning</dt>
              <dd>{toning.join(", ")}</dd>
            </>
          )}
          {showValue && (
            <>
              <dt>Est. value</dt>
              <dd>{money(c.value_estimate)}</dd>
            </>
          )}
        </dl>
      </div>
    </div>
  );
}

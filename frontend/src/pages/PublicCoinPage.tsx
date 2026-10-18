import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { api, type PublicCoin } from "../api";
import Logo from "../components/Logo";
import { coinPath, gradeLabel, slabLabel, toningLabel } from "../format";

/** Where a coin label's QR code goes. The owner is taken to their coin; anyone else sees the coin's public page if
 * the owner turned it on, or that it's private. */
export default function PublicCoinPage() {
  const { token = "" } = useParams();
  const [data, setData] = useState<PublicCoin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [i, setI] = useState(0);

  useEffect(() => {
    api
      .publicCoin(token)
      .then((d) => {
        setData(d);
        if (!d.owner && !d.private) document.title = `${d.title} · TrackMyCoins`;
      })
      .catch((e) => setError((e as Error).message));
  }, [token]);

  if (data?.owner) return <Navigate to={coinPath(data.inventory_number)} replace />;

  return (
    <div className="shared">
      <header className="shared-bar">
        <Link to="/" aria-label="TrackMyCoins home">
          <Logo size={28} />
        </Link>
        <span className="muted small">Coin · view only</span>
      </header>
      <main className="shared-main public-coin">
        {error && (
          <div className="card empty-state">
            <h2>Link Not Available</h2>
            <p className="muted">{error}</p>
          </div>
        )}
        {!data && !error && <p className="muted">Loading…</p>}
        {data && !data.owner && data.private && (
          <div className="card empty-state">
            <h2>This Coin Is Private</h2>
            <p className="muted">Its owner hasn't made a public page for it. If it's yours, sign in to see it.</p>
            <Link className="btn" to="/login" state={{ from: `/c/${token}` }}>
              Sign in
            </Link>
          </div>
        )}
        {data && !data.owner && !data.private && (
          <div className={`card public-coin-card${data.coin.photo_urls.length ? " has-photo" : ""}`}>
            {data.coin.photo_urls.length > 0 && (
              <div>
                <img className="shared-photo" src={data.coin.photo_urls[i]} alt={`${data.title}, photo ${i + 1}`} />
                {data.coin.photo_urls.length > 1 && (
                  <div className="thumb-row">
                    {data.coin.photo_urls.map((u, j) => (
                      <button key={u} className={`thumb-btn${j === i ? " active" : ""}`} onClick={() => setI(j)} aria-label={`Photo ${j + 1}`}>
                        <img src={u} alt="" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div>
              <h1>{data.title}</h1>
              <dl className="facts">
                <dt>Grade</dt>
                <dd>{gradeLabel(data.coin)}</dd>
                <dt>Graded by</dt>
                <dd>
                  {data.coin.grading_service === "RAW"
                    ? "Ungraded"
                    : `${data.coin.grading_service}${data.coin.cert_number ? ` #${data.coin.cert_number}` : ""}`}
                </dd>
                {data.coin.cac && (
                  <>
                    <dt>CAC</dt>
                    <dd style={{ textTransform: "capitalize" }}>{data.coin.cac_sticker ?? "Yes"}</dd>
                  </>
                )}
                {data.coin.variety && (
                  <>
                    <dt>Variety</dt>
                    <dd>{data.coin.variety}</dd>
                  </>
                )}
                {data.coin.vam && (
                  <>
                    <dt>VAM</dt>
                    <dd>{data.coin.vam}</dd>
                  </>
                )}
                {data.coin.is_error && data.coin.error_description && (
                  <>
                    <dt>Error</dt>
                    <dd>{data.coin.error_description}</dd>
                  </>
                )}
                {slabLabel(data.coin).length > 0 && (
                  <>
                    <dt>Holder</dt>
                    <dd>{slabLabel(data.coin).join(", ")}</dd>
                  </>
                )}
                {toningLabel(data.coin).length > 0 && (
                  <>
                    <dt>Toning</dt>
                    <dd>{toningLabel(data.coin).join(", ")}</dd>
                  </>
                )}
              </dl>
            </div>
          </div>
        )}
      </main>
      <footer className="shared-foot muted small">
        Organized with <Link to="/">TrackMyCoins</Link>
      </footer>
    </div>
  );
}

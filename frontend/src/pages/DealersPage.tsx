import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Dealer } from "../api";
import DealerDialog from "../components/DealerDialog";
import { money } from "../format";

/** Your dealers: search, scan a card or banner, add one by hand. */
export default function DealersPage() {
  const navigate = useNavigate();
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState<"scan" | "type" | null>(null);

  useEffect(() => {
    api
      .dealers()
      .then(setDealers)
      .catch((e) => setError((e as Error).message));
  }, []);

  const term = q.trim().toLowerCase();
  const shown = (dealers ?? []).filter(
    (d) =>
      !term ||
      [d.business, d.contact_name, d.notes, d.phone, d.email, ...d.specialties].some((x) => x && x.toLowerCase().includes(term)),
  );

  return (
    <div className="page dealers-page">
      <div className="page-head">
        <div>
          <h1>Dealers</h1>
          <p className="muted small">The dealers you buy from and sell to. Pick one in a coin's Purchased from or Sold to and it shows up on their page.</p>
        </div>
        <div className="row wrap">
          <button className="btn btn-primary" onClick={() => setAdding("scan")}>
            📷 Scan card or banner
          </button>
          <button className="btn" onClick={() => setAdding("type")}>
            + Add dealer
          </button>
        </div>
      </div>

      <section className="card">
        {error && <p className="error">{error}</p>}
        {!dealers && !error && <p className="muted">Loading…</p>}
        {dealers && dealers.length === 0 && (
          <div className="empty-state">
            <h2>Add Your First Dealer</h2>
            <p className="muted">At a show, snap their business card or table banner and the details fill in for you.</p>
          </div>
        )}
        {dealers && dealers.length > 0 && (
          <>
            <input
              className="dealer-search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, business, specialty, notes…"
              aria-label="Search dealers"
            />
            <ul className="dealer-list">
              {shown.map((d) => (
                <li key={d.id}>
                  <Link to={`/dealers/${d.id}`} className="dealer-row">
                    {d.photo_url ? <img src={d.photo_url} alt="" className="dealer-thumb" /> : <span className="dealer-thumb blank">🏪</span>}
                    <span className="dealer-main">
                      <strong>{d.display_name}</strong>
                      {d.business && d.contact_name && <span className="muted"> · {d.contact_name}</span>}
                      {d.specialties.length > 0 && (
                        <span className="dealer-tags">
                          {d.specialties.map((t) => (
                            <span key={t} className="tag">
                              {t}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                    <span className="dealer-stats small muted">
                      {d.bought_count ? `${d.bought_count} bought · ${money(d.bought_total ?? null)}` : ""}
                      {d.bought_count && d.sold_count ? <br /> : null}
                      {d.sold_count ? `${d.sold_count} sold · ${money(d.sold_total ?? null)}` : ""}
                      {!d.bought_count && !d.sold_count ? "No coins yet" : ""}
                    </span>
                  </Link>
                </li>
              ))}
              {shown.length === 0 && <li className="muted small">No dealers match “{q}”.</li>}
            </ul>
          </>
        )}
      </section>
      {adding && (
        <DealerDialog scanFirst={adding === "scan"} onClose={() => setAdding(null)} onSaved={(d) => navigate(`/dealers/${d.id}`)} />
      )}
    </div>
  );
}

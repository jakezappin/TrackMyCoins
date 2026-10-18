import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type DealerDetail, type DealerLinkSuggestion } from "../api";
import DealerDialog from "../components/DealerDialog";
import { loadDealers } from "../components/DealerInput";
import DownloadLink from "../components/DownloadLink";
import { coinPath, money, shortDate } from "../format";

/** One dealer: contact details and quick actions, their card photo, and everything you've bought from or sold to them. */
export default function DealerPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [d, setD] = useState<DealerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [linking, setLinking] = useState(false);

  const load = () =>
    api
      .dealer(Number(id))
      .then(setD)
      .catch((e) => setError((e as Error).message));
  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !d) return <div className="page error">{error}</div>;
  if (!d) return <div className="page muted">Loading…</div>;

  const site = d.website ? (/^https?:\/\//i.test(d.website) ? d.website : `https://${d.website}`) : null;
  const tel = d.phone ? d.phone.replace(/[^\d+]/g, "") : null;
  const bought = d.items.filter((i) => i.bought);
  const sold = d.items.filter((i) => i.sold_to_them);

  async function remove() {
    if (!confirm(`Delete ${d!.display_name}? Your coins keep the name as text, just not linked.`)) return;
    try {
      await api.deleteDealer(d!.id);
      loadDealers(true);
      navigate("/dealers");
    } catch (e) {
      alert((e as Error).message);
    }
  }

  return (
    <div className="page dealer-page">
      <Link to="/dealers" className="btn small back-link">
        ← Dealers
      </Link>
      <div className="page-head">
        <div>
          <h1>{d.display_name}</h1>
          {d.business && d.contact_name && <p className="muted">{d.contact_name}</p>}
        </div>
        <div className="row wrap">
          {tel && (
            <>
              <a className="btn" href={`tel:${tel}`} aria-label={`Call ${d.display_name}`}>
                📞 Call
              </a>
              <a className="btn" href={`sms:${tel}`} aria-label={`Text ${d.display_name}`}>
                💬 Text
              </a>
            </>
          )}
          {d.email && (
            <a className="btn" href={`mailto:${d.email}`}>
              ✉️ Email
            </a>
          )}
          {site && (
            <a className="btn" href={site} target="_blank" rel="noreferrer">
              🌐 Website
            </a>
          )}
          <DownloadLink href={api.dealerVcardUrl(d.id)} className="btn">
            Save to phone contacts
          </DownloadLink>
          <button className="btn" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button className="btn danger" onClick={remove}>
            Delete
          </button>
        </div>
      </div>

      <div className="coin-row">
        <section className="card dealer-contact">
          <dl className="facts">
            {d.phone && (
              <>
                <dt>Phone</dt>
                <dd>{d.phone}</dd>
              </>
            )}
            {d.email && (
              <>
                <dt>Email</dt>
                <dd>{d.email}</dd>
              </>
            )}
            {d.website && (
              <>
                <dt>Website</dt>
                <dd>{site ? <a href={site} target="_blank" rel="noreferrer">{d.website}</a> : d.website}</dd>
              </>
            )}
            {d.address && (
              <>
                <dt>Address</dt>
                <dd>{d.address}</dd>
              </>
            )}
            {d.social && (
              <>
                <dt>Social</dt>
                <dd>{d.social}</dd>
              </>
            )}
          </dl>
          {d.specialties.length > 0 && (
            <div className="dealer-tags">
              {d.specialties.map((t) => (
                <span key={t} className="tag">
                  {t}
                </span>
              ))}
            </div>
          )}
          {d.notes && <p className="dealer-notes">{d.notes}</p>}
          {!d.phone && !d.email && !d.website && !d.notes && <p className="muted small">No contact details yet. Edit to add them.</p>}
        </section>
        {d.photo_url && (
          <section className="card dealer-photo-card">
            <a href={d.photo_url} target="_blank" rel="noreferrer">
              <img src={d.photo_url} alt={`${d.display_name}'s card or banner`} className="dealer-card-photo big" />
            </a>
          </section>
        )}
      </div>

      <div className="cards dealer-summary">
        <div className="card stat">
          <div className="stat-label">Bought from them</div>
          <div className="stat-value">{money(d.bought_total ?? null)}</div>
          <div className="stat-note">
            {d.bought_count} item{d.bought_count === 1 ? "" : "s"}
          </div>
        </div>
        <div className="card stat">
          <div className="stat-label">Sold to them</div>
          <div className="stat-value">{money(d.sold_total ?? null)}</div>
          <div className="stat-note">
            {d.sold_count} item{d.sold_count === 1 ? "" : "s"}
          </div>
        </div>
        <div className="card stat">
          <div className="stat-label">What you bought is worth now</div>
          <div className="stat-value">{d.held_value != null ? money(d.held_value) : "—"}</div>
          <div className="stat-note">
            {d.held_count} still held{d.held_unvalued ? ` · ${d.held_unvalued} not priced yet` : ""}
          </div>
        </div>
      </div>

      {d.link_suggestions > 0 && (
        <p className="banner">
          {d.link_suggestions === 1 ? "1 coin names" : `${d.link_suggestions} coins name`} {d.display_name} in Purchased from or Sold to but
          {d.link_suggestions === 1 ? " isn't" : " aren't"} linked yet.{" "}
          <button className="link-btn" onClick={() => setLinking(true)}>
            Link my coins
          </button>
        </p>
      )}

      <section className="card">
        <h2>History</h2>
        {d.items.length === 0 ? (
          <p className="muted small">
            Nothing yet. Pick {d.display_name} in a coin's Purchased from or Sold to and it shows up here.
          </p>
        ) : (
          <div className="table-scroll">
            <table className="history dealer-history">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Bought</th>
                  <th className="num">Paid</th>
                  <th>Sold</th>
                  <th className="num">Sale price</th>
                  <th className="num">Worth now</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((i) => (
                  <tr key={`${i.kind}-${i.inventory_number}`}>
                    <td>
                      <Link to={i.kind === "coin" ? coinPath(i.inventory_number) : `/bullion/items/${i.inventory_number}`}>{i.title}</Link>
                      <div className="muted small">
                        {i.inventory_number}
                        {i.bought && i.sold_to_them ? " · bought from and sold back to them" : i.sold_to_them ? " · sold to them" : ""}
                      </div>
                    </td>
                    <td className="small">{i.bought && i.purchase_date ? shortDate(i.purchase_date) : ""}</td>
                    <td className="num">{i.bought ? money(i.price_paid) : ""}</td>
                    <td className="small">{i.is_sold && i.sale_date ? shortDate(i.sale_date) : ""}</td>
                    <td className="num">{i.is_sold ? money(i.sale_price) : ""}</td>
                    <td className="num">{i.value_now != null ? money(i.value_now) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          {bought.length} bought · {sold.length} sold to them
        </p>
      </section>

      {editing && (
        <DealerDialog
          dealer={d}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            load();
          }}
        />
      )}
      {linking && (
        <LinkDialog
          dealerId={d.id}
          name={d.display_name}
          onClose={() => setLinking(false)}
          onDone={(next) => {
            setD(next);
            setLinking(false);
          }}
        />
      )}
    </div>
  );
}

/** Coins typed before the dealer was added ("Ricks Rare Coins"): tick the ones to link. */
function LinkDialog({ dealerId, name, onClose, onDone }: { dealerId: number; name: string; onClose: () => void; onDone: (d: DealerDetail) => void }) {
  const [rows, setRows] = useState<DealerLinkSuggestion[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = (r: DealerLinkSuggestion) => `${r.kind}:${r.inventory_number}`;

  useEffect(() => {
    api
      .dealerLinkSuggestions(dealerId)
      .then((r) => {
        setRows(r);
        setPicked(new Set(r.map(key)));
      })
      .catch((e) => setError((e as Error).message));
  }, [dealerId]);

  async function link() {
    setBusy(true);
    try {
      onDone(await api.linkDealerItems(dealerId, [...picked]));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Link coins" onClick={(e) => e.stopPropagation()}>
        <h2>Link Coins to {name}</h2>
        <p className="muted small">These name {name} in Purchased from or Sold to. Untick any that are someone else.</p>
        {error && <p className="error small">{error}</p>}
        {!rows && !error && <p className="muted">Loading…</p>}
        {rows && (
          <ul className="link-list">
            {rows.map((r) => (
              <li key={key(r)}>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={picked.has(key(r))}
                    onChange={(e) => {
                      const next = new Set(picked);
                      if (e.target.checked) next.add(key(r));
                      else next.delete(key(r));
                      setPicked(next);
                    }}
                  />
                  <span>
                    {r.title} <span className="muted small">{r.inventory_number}</span>
                    <br />
                    <span className="muted small">
                      {r.fields.includes("purchased_from") && `Purchased from “${r.purchased_from}”`}
                      {r.fields.length > 1 ? " · " : ""}
                      {r.fields.includes("sold_to") && `Sold to “${r.sold_to}”`}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="row-end">
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={link} disabled={busy || !picked.size}>
            {busy ? "Linking…" : `Link ${picked.size}`}
          </button>
        </div>
      </div>
    </div>
  );
}

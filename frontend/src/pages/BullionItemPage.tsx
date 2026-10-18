import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type BullionItem } from "../api";
import { useApp } from "../App";
import { METAL_LABEL, ozLabel, purityLabel, quantityLabel, weightLabel } from "../bullionFormat";
import CoinPlaceholder from "../components/CoinPlaceholder";
import PhotoButtons from "../components/PhotoButtons";
import ValueHistoryChart from "../components/ValueHistoryChart";
import { money, parseMoney, shortDate, todayISO } from "../format";

const signed = (v: string | number | null | undefined) => {
  if (v == null) return "—";
  const n = Number(v);
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${money(Math.abs(n))}`;
};
const tone = (v: string | number | null | undefined) => (v == null || Number(v) === 0 ? "" : Number(v) > 0 ? "pos" : "neg");

/** One bullion item: melt value now and at purchase, photos, details, value over time, and selling. */
export default function BullionItemPage() {
  const { inv = "" } = useParams();
  const navigate = useNavigate();
  const { refresh } = useApp();
  const [item, setItem] = useState<BullionItem | null>(null);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selling, setSelling] = useState(false);
  const busyRef = useRef(false);

  useEffect(() => {
    setItem(null);
    api.bullionItem(inv).then(setItem).catch((e) => setError((e as Error).message));
  }, [inv]);

  async function act(label: string, fn: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  if (error && !item) return <div className="page error">{error}</div>;
  if (!item) return <div className="page muted">Loading…</div>;
  const photo = item.photos[active];
  const sold = item.is_sold;

  return (
    <div className="page coin-page">
      <div>
        <Link className="btn back-btn" to={`/bullion/${item.collection_id}`}>
          ← Back to {item.collection_name}
        </Link>
      </div>
      {(error || busy) && <p className={error ? "error banner" : "muted banner"}>{error ?? `${busy}…`}</p>}
      <div className="page-head">
        <div>
          <h1>
            {item.description}
            {sold && <span className="tag sold big">Sold</span>}
          </h1>
          <p className="muted">
            {item.inventory_number} · {METAL_LABEL[item.metal]} · {purityLabel(item.purity)}
          </p>
        </div>
        <div className="row">
          <button
            className="btn danger-outline"
            disabled={busy !== null}
            onClick={() =>
              confirm(`Delete ${item.inventory_number}?`) &&
              act("Deleting", async () => {
                await api.deleteBullionItem(item.inventory_number);
                await refresh();
                navigate(`/bullion/${item.collection_id}`);
              })
            }
          >
            Delete
          </button>
          {!sold && (
            <button className="btn" onClick={() => setSelling(true)}>
              Sell…
            </button>
          )}
          <Link className="btn btn-primary" to={`/bullion/items/${item.inventory_number}/edit`}>
            Edit
          </Link>
        </div>
      </div>

      <div className="coin-summary">
        <div className="card stat">
          <div className="stat-label">{sold ? "Sold For" : "Melt Value"}</div>
          <div className="stat-value">{money(sold ? item.sale_price : item.value_now)}</div>
          <div className="stat-note">
            {sold ? (item.sale_date ? shortDate(item.sale_date) : "Sold") : item.spot_now ? `${money(item.spot_now)}/ozt spot` : "Spot unavailable"}
          </div>
        </div>
        <div className="card stat">
          <div className="stat-label">Paid</div>
          <div className="stat-value">{money(item.price_paid)}</div>
          <div className="stat-note">{item.purchase_date ? shortDate(item.purchase_date) : "No purchase date"}</div>
        </div>
        <div className="card stat">
          <div className="stat-label">{sold ? "Profit / Loss" : "Change"}</div>
          <div className={`stat-value ${tone(item.change)}`}>{signed(item.change)}</div>
          <div className="stat-note">{item.change_pct == null ? "Needs what you paid" : `${item.change_pct > 0 ? "+" : ""}${item.change_pct}%`}</div>
        </div>
        <div className="card stat">
          <div className="stat-label">Melt at Purchase</div>
          <div className="stat-value">{money(item.value_at_purchase)}</div>
          <div className="stat-note">
            {item.value_at_purchase == null
              ? "No spot price on file for that date"
              : `${money(item.spot_at_purchase)}/ozt${item.premium_pct != null ? ` · ${item.premium_pct >= 0 ? `${item.premium_pct}% premium` : `${-item.premium_pct}% under melt`}` : ""}`}
          </div>
        </div>
      </div>

      <div className="coin-row">
        <section className="card gallery">
          {photo ? (
            <div className="hero-photo">
              <img src={photo.url} alt="" />
              <div className="photo-actions">
                <button
                  className="btn small danger-outline"
                  disabled={busy !== null}
                  onClick={() =>
                    act("Deleting the photo", async () => {
                      await api.deleteBullionPhoto(photo.id);
                      setActive(0);
                      setItem(await api.bullionItem(item.inventory_number));
                    })
                  }
                >
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <div className="hero-photo empty">
              <CoinPlaceholder className="ph-hero" metal={item.metal === "gold" ? "gold" : "silver"} date={METAL_LABEL[item.metal]} typeName={item.description} />
            </div>
          )}
          {item.photos.length > 1 && (
            <div className="thumb-row">
              {item.photos.map((p, i) => (
                <button key={p.id} className={`thumb-btn ${i === active ? "active" : ""}`} onClick={() => setActive(i)}>
                  <img src={p.thumb_url} alt="" loading="lazy" />
                </button>
              ))}
            </div>
          )}
          <div className="photo-foot">
            <span className="muted small">{item.photos.length} / 10 photos</span>
            {item.photos.length < 10 && (
              <PhotoButtons
                takeLabel={busy === "Uploading" ? "Uploading…" : "Take photo"}
                chooseLabel="Add photos"
                disabled={busy !== null}
                onFiles={(fs) => act("Uploading", async () => setItem(await api.uploadBullionPhotos(item.inventory_number, fs)))}
              />
            )}
          </div>
        </section>

        <section className="card details-card">
          <h2>Details</h2>
          <dl className="facts">
            <dt>Amount</dt>
            <dd>
              {weightLabel(item)}
              {item.face_value == null && <span className="muted"> · {quantityLabel(item)}</span>}
            </dd>
            <dt>Purity</dt>
            <dd>{purityLabel(item.purity)}</dd>
            <dt>Pure {METAL_LABEL[item.metal].toLowerCase()}</dt>
            <dd>{ozLabel(item.oz)}</dd>
          </dl>
          <h3 className="details-sub">Purchase</h3>
          <dl className="facts">
            <dt>Paid</dt>
            <dd>
              {money(item.price_paid)} {item.purchase_date && <span className="muted">on {shortDate(item.purchase_date)}</span>}
            </dd>
            <dt>From</dt>
            <dd>{item.purchased_from ?? "—"}</dd>
            <dt>Melt then</dt>
            <dd>{money(item.value_at_purchase)}</dd>
          </dl>
          {sold && (
            <>
              <h3 className="details-sub">Sale</h3>
              <dl className="facts">
                <dt>Sold</dt>
                <dd>
                  {money(item.sale_price)} {item.sale_date && <span className="muted">on {shortDate(item.sale_date)}</span>}
                  {item.sold_to && <span className="muted"> to {item.sold_to}</span>}
                </dd>
              </dl>
            </>
          )}
          {item.notes && <p className="notes">{item.notes}</p>}
        </section>
      </div>

      <ValueHistoryChart
        coinInv={item.inventory_number}
        load={() => api.bullionItemHistory(item.inventory_number)}
        refreshKey={`${item.value_now}-${item.quantity}`}
        title="Melt Value Over Time"
        valueLabel="Melt value"
        emptyText="The chart fills in from the purchase date as daily spot prices are recorded."
      />

      {selling && (
        <SellDialog
          item={item}
          onClose={() => setSelling(false)}
          onSold={async (r) => {
            setSelling(false);
            await refresh();
            navigate(`/bullion/items/${r.kept ?? r.sold}`);
            if (r.kept) setItem(await api.bullionItem(r.kept));
          }}
        />
      )}
    </div>
  );
}

function SellDialog({ item, onClose, onSold }: { item: BullionItem; onClose: () => void; onSold: (r: { sold: string; kept: string | null }) => void }) {
  const byFace = item.face_value != null;
  const many = !byFace && item.quantity > 1;
  const [part, setPart] = useState(byFace ? String(Number(item.face_value)) : String(item.quantity));
  const [price, setPrice] = useState("");
  const [day, setDay] = useState(todayISO());
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sell() {
    const p = parseMoney(price);
    if ("error" in p || p.value == null) return setError(`Sale price ${"error" in p ? p.error : "is required"}.`);
    setBusy(true);
    setError(null);
    try {
      const body = {
        sale_price: p.value,
        sale_date: day,
        sold_to: to || null,
        ...(byFace ? { face_value: part } : many ? { quantity: Number(part) } : {}),
      };
      onSold(await api.sellBullion(item.inventory_number, body));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const whole = byFace ? Number(part) >= Number(item.face_value) : !many || Number(part) >= item.quantity;
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Sell" onClick={(e) => e.stopPropagation()}>
        <h2>Sell {item.description}</h2>
        {(many || byFace) && (
          <label className="field">
            <span>{byFace ? `Face value sold (of $${Number(item.face_value)})` : `Pieces sold (of ${item.quantity})`}</span>
            <input type="number" min={byFace ? 0.01 : 1} max={byFace ? Number(item.face_value) : item.quantity} step={byFace ? 0.01 : 1} value={part} onChange={(e) => setPart(e.target.value)} />
            <small className="muted">
              {whole
                ? "All of it."
                : byFace
                  ? `$${(Number(item.face_value) - Number(part)).toFixed(2)} face stays on hand as ${item.inventory_number}; the sold part gets its own number.`
                  : `${item.quantity - Number(part)} stay on hand as ${item.inventory_number}; the sold pieces get their own number and their share of the cost.`}
            </small>
          </label>
        )}
        <div className="grid-2">
          <label className="field">
            <span>Sale price (total)</span>
            <input type="text" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" autoFocus />
          </label>
          <label className="field">
            <span>Sale date</span>
            <input type="date" max={todayISO()} value={day} onChange={(e) => setDay(e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span>Sold to (optional)</span>
          <input value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={sell}>
            {busy ? "Saving…" : "Record sale"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

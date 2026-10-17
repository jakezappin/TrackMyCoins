import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type CoinDetail } from "../api";
import { useApp } from "../App";
import NgcPhotoLink from "../components/NgcPhotoLink";
import { ngcCertUrl } from "../ngcButton";
import PhotoButtons from "../components/PhotoButtons";
import CoinPlaceholder from "../components/CoinPlaceholder";
import EstimatedValueCard from "../components/EstimatedValueCard";
import CoinFactsCard from "../components/CoinFactsCard";
import EbayCard from "../components/EbayCard";
import GradePricesCard from "../components/GradePricesCard";
import PcgsMarketCard from "../components/PcgsMarketCard";
import {
  coinPath,
  collectionPath,
  metalFor,
  dateMint,
  gradeLabel,
  money,
  profit,
  shortDate,
  slabLabel,
  soldPath,
  parseMoney,
  toningLabel,
} from "../format";

const SOURCE_LABEL: Record<string, string> = {
  CPG: "CPG",
  PCGS: "PCGS Guide",
  PREMIUM: "CPG + premiums",
  CUSTOM: "Your value",
  GREYSHEET: "Greysheet",
};

export default function CoinDetailPage() {
  const inv = useParams().inv ?? "";
  const navigate = useNavigate();
  const { refresh, coinTypes } = useApp();
  const [coin, setCoin] = useState<CoinDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [cpgBusy, setCpgBusy] = useState(false);
  const [cpgError, setCpgError] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pcgsBusy, setPcgsBusy] = useState(false);
  const [pcgsError, setPcgsError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.coin(inv).then(setCoin).catch((e) => setError(e.message));
  }, [inv]);

  function update(c: CoinDetail) {
    setCoin(c);
    refresh();
  }

  async function getCpg() {
    setCpgBusy(true);
    setCpgError(null);
    try {
      update(await api.getCpg(inv));
    } catch (e) {
      setCpgError((e as Error).message);
    } finally {
      setCpgBusy(false);
    }
  }

  async function getPcgs() {
    setPcgsBusy(true);
    setPcgsError(null);
    try {
      update(await api.getPcgs(inv));
    } catch (e) {
      setPcgsError((e as Error).message);
    } finally {
      setPcgsBusy(false);
    }
  }

  /** Run an action, showing its error instead of failing silently; one at a time (no double taps). */
  async function act(label: string, fn: () => Promise<void>) {
    // A ref, not state: two taps in the same instant both see state as "not busy" until the next render.
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyAction(label);
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(`${label} failed: ${(err as Error).message}`);
    } finally {
      busyRef.current = false;
      setBusyAction(null);
    }
  }

  async function addManual(e: React.FormEvent) {
    e.preventDefault();
    const r = parseMoney(manual);
    if ("error" in r || r.value === null) {
      setCpgError("error" in r ? `That value ${r.error}.` : "Enter a value.");
      return;
    }
    setCpgError(null);
    await act("Adding the price", async () => {
      update(await api.addQuote(inv, r.value!));
      setManual("");
    });
  }

  function removeQuote(qid: number) {
    if (!confirm("Remove this price from the history?")) return;
    return act("Removing the price", async () => {
      await api.deleteQuote(qid);
      update(await api.coin(inv));
    });
  }

  function upload(files: FileList | File[] | null) {
    if (!files?.length) return;
    const list = Array.from(files);
    return act(`Uploading ${list.length} photo${list.length === 1 ? "" : "s"}`, async () => {
      try {
        update(await api.uploadPhotos(inv, list));
      } finally {
        if (fileRef.current) fileRef.current.value = "";
      }
    });
  }

  function removePhoto(pid: number) {
    if (!confirm("Delete this photo?")) return;
    return act("Deleting the photo", async () => {
      await api.deletePhoto(pid);
      setActive(0);
      update(await api.coin(inv));
    });
  }

  function makePrimary(pid: number) {
    if (!coin) return;
    const order = [pid, ...coin.photos.map((p) => p.id).filter((x) => x !== pid)];
    return act("Making it the main photo", async () => {
      update(await api.reorderPhotos(inv, order));
      setActive(0);
    });
  }

  function removeCoin() {
    if (!coin || !confirm(`Delete ${coin.inventory_number} (${dateMint(coin)} ${gradeLabel(coin)})? This can't be undone.`)) return;
    return act("Deleting the coin", async () => {
      await api.deleteCoin(inv);
      await refresh();
      navigate(collectionPath({ collection_type_slug: coin.collection_type_slug, number: coin.collection_number }));
    });
  }

  if (error) return <div className="page error">{error}</div>;
  if (!coin) return <div className="page muted">Loading…</div>;

  const photo = coin.photos[active];
  const pl = profit(coin);
  const toning = toningLabel(coin);
  const slabs = slabLabel(coin);

  return (
    <div className="page">
      <div>
        <Link
          className="btn back-btn"
          to={
            coin.is_sold
              ? soldPath(coin.coin_type_slug)
              : collectionPath({ collection_type_slug: coin.collection_type_slug, number: coin.collection_number })
          }
        >
          ← Back to {coin.is_sold ? "Sold" : coin.collection_name}
        </Link>
      </div>
      {(actionError || busyAction) && (
        <p className={actionError ? "error banner" : "muted banner"} role={actionError ? "alert" : "status"}>
          {actionError ?? `${busyAction}…`}
          {actionError && (
            <button type="button" className="link-btn" onClick={() => setActionError(null)}>
              Dismiss
            </button>
          )}
        </p>
      )}
      <div className="page-head">
        <div>
          <h1>
            {dateMint(coin)} {coinTypes.find((t) => t.id === coin.coin_type_id)?.name ?? ""} {gradeLabel(coin)}
            {coin.is_sold && <span className="tag sold big">Sold</span>}
          </h1>
          <p className="muted">
            {coin.inventory_number} · {coin.grading_service === "RAW" ? "Raw (ungraded)" : coin.grading_service}
            {coin.cert_number && ` #${coin.cert_number}`}
            {coin.vam && ` · ${coin.vam}`}
          </p>
        </div>
        <div className="row">
          <button className="btn danger-outline" onClick={removeCoin} disabled={busyAction !== null}>
            Delete
          </button>
          <Link className="btn btn-primary" to={`${coinPath(inv)}/edit`}>
            Edit
          </Link>
        </div>
      </div>

      <div className="detail-grid">
        {/* Photos */}
        <div className="stack">
        <section className="card gallery">
          {photo ? (
            <div className="hero-photo">
              <img src={photo.url} alt="" />
              <div className="photo-actions">
                {active !== 0 && (
                  <button className="btn small" onClick={() => makePrimary(photo.id)} disabled={busyAction !== null}>
                    Make primary
                  </button>
                )}
                <button className="btn small danger-outline" onClick={() => removePhoto(photo.id)} disabled={busyAction !== null}>
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <div className="hero-photo empty">
              <CoinPlaceholder
                className="ph-hero"
                metal={metalFor(coinTypes, coin.coin_type_id)}
                date={dateMint(coin)}
                typeName={coinTypes.find((t) => t.id === coin.coin_type_id)?.name}
              />
              <button className="btn btn-primary ph-add" onClick={() => fileRef.current?.click()} disabled={busyAction !== null}>
                + Add photos
              </button>
            </div>
          )}
          <div className="thumb-row">
            {coin.photos.map((p, i) => (
              <button key={p.id} className={`thumb-btn ${i === active ? "active" : ""}`} onClick={() => setActive(i)}>
                <img src={p.thumb_url} alt="" loading="lazy" />
              </button>
            ))}
            {coin.photos.length > 0 && coin.photos.length < 10 && (
              <button className="thumb-btn add" onClick={() => fileRef.current?.click()} title="Add photos" aria-label="Add photos" disabled={busyAction !== null}>
                +
              </button>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
          <div className="photo-foot">
            <span className="muted small">{coin.photos.length} / 10 photos</span>
            {coin.photos.length < 10 && (
              <PhotoButtons
                takeLabel={busyAction?.startsWith("Uploading") ? "Uploading…" : "Take photo"}
                chooseLabel="Add photos"
                disabled={busyAction !== null}
                onFiles={(fs) => upload(fs)}
              />
            )}
          </div>
          {coin.grading_service === "NGC" && coin.photos.length <= 8 && (
            <details className="ngc-add" open={coin.photos.length === 0}>
              <summary className="small">Add NGC's photos</summary>
              {coin.cert_number && (
                <p className="small muted">
                  Open{" "}
                  <a href={ngcCertUrl(coin.cert_number, coin.grade)} target="_blank" rel="noreferrer">
                    this coin on NGC ↗
                  </a>
                  , then copy a coin photo's address there and paste it below.
                </p>
              )}
              <NgcPhotoLink
                expectedCert={coin.cert_number}
                actionLabel="Add photos"
                busyLabel="Adding…"
                onFound={async (r) => update(await api.importPhotos(inv, r.urls))}
              />
            </details>
          )}
        </section>
        <CoinFactsCard
          facts={coin.facts}
          canFetch={Boolean(coin.grade && (coin.pcgs_number || coin.grading_service !== "RAW"))}
          busy={pcgsBusy}
          onFetch={getPcgs}
        />
        <GradePricesCard
          inv={coin.inventory_number}
          grade={coin.grade}
          gradePlus={coin.grade_plus}
          cac={coin.cac}
          refreshKey={coin.latest_cpg?.id}
          canFetch={Boolean(coin.grade)}
          busy={cpgBusy}
          onFetch={getCpg}
        />
        </div>

        {/* Facts + pricing */}
        <div className="stack">
          <section className="card">
            <h2>Details</h2>
            <dl className="facts">
              <dt>Grade</dt>
              <dd>{gradeLabel(coin)}</dd>
              {coin.variety && (
                <>
                  <dt>Variety</dt>
                  <dd>{coin.variety}</dd>
                </>
              )}
              <dt>CAC</dt>
              <dd>
                {coin.cac ? <span className={`tag cac-${coin.cac_sticker ?? "green"}`}>CAC {coin.cac_sticker ?? ""}</span> : "No"}
              </dd>
              <dt>Slab / holder</dt>
              <dd>{slabs.length ? slabs.join(", ") : "—"}</dd>
              <dt>Toning</dt>
              <dd>{toning.length ? toning.join(", ") : "—"}</dd>
              <dt>PCGS #</dt>
              <dd>{coin.pcgs_number ?? "—"}</dd>
              <dt>Paid</dt>
              <dd>
                {money(coin.price_paid)} {coin.purchase_date && <span className="muted">on {shortDate(coin.purchase_date)}</span>}
              </dd>
              <dt>From</dt>
              <dd>{coin.purchased_from ?? "—"}</dd>
              {coin.is_sold && (
                <>
                  <dt>Sold</dt>
                  <dd>
                    {money(coin.sale_price)} {coin.sale_date && <span className="muted">on {shortDate(coin.sale_date)}</span>}
                    {coin.sold_to && <span className="muted"> to {coin.sold_to}</span>}
                  </dd>
                  <dt>Profit / loss</dt>
                  <dd className={pl == null ? "" : pl >= 0 ? "pos" : "neg"}>{pl == null ? "—" : money(pl)}</dd>
                </>
              )}
            </dl>
            {coin.notes && <p className="notes">{coin.notes}</p>}
          </section>

          <EstimatedValueCard coin={coin} onChange={update} />

          <section className="card">
            <div className="section-head">
              <h2>CPG Value</h2>
              <button className="btn btn-primary" onClick={getCpg} disabled={cpgBusy}>
                {cpgBusy ? "Fetching…" : "Get CPG Price"}
              </button>
            </div>
            <div className="big-number">{money(coin.latest_cpg?.value)}</div>
            {coin.latest_cpg && (
              <p className="muted small">
                {coin.latest_cpg.grade_used && `Grade ${coin.latest_cpg.grade_used} · `}as of {shortDate(coin.latest_cpg.confirmed_at ?? coin.latest_cpg.fetched_at)}
              </p>
            )}
            {coin.latest_greysheet && (
              <p className="small">
                Greysheet (wholesale): <strong>{money(coin.latest_greysheet.value)}</strong>
              </p>
            )}
            {cpgError && <p className="error small">{cpgError}</p>}
            <form className="row tight manual-quote" onSubmit={addManual}>
              <input
                type="text"
                inputMode="decimal"
                placeholder="Enter CPG value by hand"
                aria-label="CPG value entered by hand"
                value={manual}
                onChange={(e) => setManual(e.target.value)}
              />
              <button className="btn" disabled={!manual || busyAction !== null}>
                {busyAction === "Adding the price" ? "Adding…" : "Add"}
              </button>
            </form>

            {coin.price_quotes.length > 0 && (
              <table className="history">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Source</th>
                    <th>Grade</th>
                    <th className="num">Value</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {coin.price_quotes.map((q) => (
                    <tr key={q.id}>
                      <td>{shortDate(q.fetched_at)}</td>
                      <td title={q.description ?? undefined}>{SOURCE_LABEL[q.source] ?? q.source}</td>
                      <td>{q.grade_used ?? "—"}</td>
                      <td className="num">{money(q.value)}</td>
                      <td>
                        <button
                          className="link-btn small icon-x"
                          onClick={() => removeQuote(q.id)}
                          aria-label={`Remove the ${SOURCE_LABEL[q.source] ?? q.source} price of ${money(q.value)}`}
                          disabled={busyAction !== null}
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      </div>

      <PcgsMarketCard
        market={coin.pcgs_market}
        cpgValue={coin.latest_cpg?.value ?? null}
        busy={pcgsBusy}
        error={pcgsError}
        onFetch={getPcgs}
      />
      {!coin.is_sold && <EbayCard inv={coin.inventory_number} />}
    </div>
  );
}

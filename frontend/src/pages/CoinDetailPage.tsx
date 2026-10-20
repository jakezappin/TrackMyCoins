import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, isPcgsLimit, type CatalogCandidate, type CatalogChoice, type CoinDetail, type CoinPublicState } from "../api";
import { useApp, useNavCollection } from "../App";
import NgcPhotoLink from "../components/NgcPhotoLink";
import { ngcCertUrl } from "../ngcButton";
import PhotoButtons from "../components/PhotoButtons";
import CoinPlaceholder from "../components/CoinPlaceholder";
import AttachmentsCard from "../components/AttachmentsCard";
import EstimatedValueCard from "../components/EstimatedValueCard";
import CoinFactsCard from "../components/CoinFactsCard";
import MoveCoin from "../components/MoveCoin";
import EbayCard from "../components/EbayCard";
import GradePricesCard from "../components/GradePricesCard";
import PcgsMarketCard from "../components/PcgsMarketCard";
import ValueHistoryChart from "../components/ValueHistoryChart";
import {
  coinPath,
  collectionPath,
  metalFor,
  dateMint,
  gradeLabel,
  money,
  profit,
  setLineName,
  shortDate,
  slabLabel,
  soldPath,
  parseMoney,
  toningLabel,
  serviceLabel,
} from "../format";

const SOURCE_LABEL: Record<string, string> = {
  CPG: "CPG",
  PCGS: "PCGS Guide",
  PREMIUM: "CPG + premiums",
  CUSTOM: "Your value",
  GREYSHEET: "Greysheet",
};

// The PCGS Market box is off for now (PCGS allows 100 lookups a day for the whole site).
const SHOW_PCGS_MARKET = false;

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
  useNavCollection("coin", coin && !coin.is_sold ? coin.collection_id : null);

  useEffect(() => {
    // Another coin: don't show the previous one (or its error) while this one loads.
    setCoin(null);
    setError(null);
    setActive(0);
    api.coin(inv).then(setCoin).catch((e) => setError(e.message));
  }, [inv]);

  // Value at purchase from PCGS auction sales: looked up once, the first time the coin needs it.
  const pvTried = useRef<string | null>(null);
  const pvPending = Boolean(coin?.purchase_value?.pending);
  useEffect(() => {
    if (!pvPending || pvTried.current === inv) return;
    pvTried.current = inv;
    api
      .fillPurchaseValue(inv)
      .then(setCoin)
      .catch(() => undefined); // e.g. today's PCGS allowance used up: price paid stands in, tried again later
  }, [pvPending, inv]);

  function update(c: CoinDetail) {
    setCoin(c);
    refresh();
  }

  // More than one catalog listing fits: the user picks one, it's saved on the coin, and the lookup runs again.
  const [choice, setChoice] = useState<{ candidates: CatalogCandidate[]; then: "cpg" | "pcgs" } | null>(null);
  const asChoice = (e: unknown) =>
    e instanceof ApiError && e.status === 409 && (e.detail as CatalogChoice | undefined)?.candidates
      ? (e.detail as CatalogChoice).candidates
      : null;

  async function getCpg() {
    setCpgBusy(true);
    setCpgError(null);
    try {
      update(await api.getCpg(inv));
    } catch (e) {
      const cands = asChoice(e);
      if (cands) setChoice({ candidates: cands, then: "cpg" });
      else setCpgError((e as Error).message);
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
      const cands = asChoice(e);
      if (cands) setChoice({ candidates: cands, then: "pcgs" });
      else setPcgsError((e as Error).message);
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
  const coinType = coinTypes.find((t) => t.id === coin.coin_type_id);
  const isSet = Boolean(coinType?.is_set); // mint & proof sets: ungraded, in OGP

  return (
    <div className="page coin-page">
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
      {coin.grading && (
        <p className="banner grading-banner">
          Out at {coin.grading.company_label} in{" "}
          <Link to={`/grading/${coin.grading.id}`}>
            submission #{coin.grading.number}
            {coin.grading.name ? ` (${coin.grading.name})` : ""}
          </Link>
          {coin.grading.expected_grade ? ` · expecting ${coin.grading.expected_grade}` : ""}. When it's back, record its result on
          the submission.
        </p>
      )}
      <div className="page-head">
        <div>
          <h1>
            {dateMint(coin)} {coinType?.name ?? ""} {isSet ? (setLineName(coin.variety) === "Main set" ? "" : setLineName(coin.variety)) : gradeLabel(coin)}
            {coin.is_sold && <span className="tag sold big">Sold</span>}
            {coin.location === "grading" && <span className="tag grading big">At Grading</span>}
            {coin.is_error && <span className="tag error big">Error</span>}
          </h1>
          <p className="muted">
            {coin.inventory_number} ·{" "}
            {isSet ? slabs.join(", ") || "Out of OGP" : coin.grading_service === "RAW" ? "Raw (ungraded)" : serviceLabel(coin.grading_service, coin.other_service)}
            {coin.cert_number && ` #${coin.cert_number}`}
            {coin.vam && ` · ${coin.vam}`}
          </p>
        </div>
        <div className="row">
          <button className="btn danger-outline" onClick={removeCoin} disabled={busyAction !== null}>
            Delete
          </button>
          <MoveCoin
            coin={coin}
            onMoved={(c) => {
              update(c);
              refresh();
            }}
          />
          {!coin.is_sold && (
            <Link className="btn" to={`/labels?coin=${encodeURIComponent(coin.inventory_number)}`}>
              Print label
            </Link>
          )}
          <Link className="btn btn-primary" to={`${coinPath(inv)}/edit`}>
            Edit
          </Link>
        </div>
      </div>

      <CoinSummary coin={coin} />

      {/* Rows keep cards side by side and aligned; on phones each row stacks. */}
      <div className="coin-row">
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
          {coin.grading_service === "PCGS" && coin.cert_number && <PcgsCheck inv={inv} cert={coin.cert_number} onDone={update} />}
          {coin.grading_service === "NGC" && coin.photos.length <= 8 && (
            <details className="ngc-add" open={coin.photos.length === 0}>
              <summary className="small">Add NGC's photos</summary>
              {coin.cert_number && (
                <p className="small muted">
                  Open{" "}
                  <a href={ngcCertUrl(coin.cert_number, coin.grade, coin.details)} target="_blank" rel="noreferrer">
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

        <section className="card details-card">
          <h2>Details</h2>
          {isSet ? (
            <dl className="facts">
              <dt>Set</dt>
              <dd>{coin.variety ?? "—"}</dd>
              <dt>Packaging</dt>
              <dd>{slabs.length ? slabs.join(", ") : "Out of OGP"}</dd>
              <dt>Toning</dt>
              <dd>{toning.length ? toning.join(", ") : "—"}</dd>
              <dt>PCGS #</dt>
              <dd>{coin.pcgs_number ?? "—"}</dd>
            <dt>Stored in</dt>
            <dd>
              {coin.storage_id ? (
                <Link to={`/storage/${coin.storage_id}`}>
                  {coin.storage_name}
                  {coin.storage_position ? ` · ${coin.storage_position}` : ""}
                </Link>
              ) : (
                "—"
              )}
            </dd>
            </dl>
          ) : (
          <dl className="facts">
            <dt>Grade</dt>
            <dd>{gradeLabel(coin)}</dd>
            {coin.is_error && (
              <>
                <dt>Error</dt>
                <dd>{coin.error_description}</dd>
              </>
            )}
            <dt>Graded by</dt>
            <dd>
              {coin.grading_service === "RAW" ? "Raw (ungraded)" : serviceLabel(coin.grading_service, coin.other_service)}
              {coin.cert_number && <span className="muted"> #{coin.cert_number}</span>}
            </dd>
            {coin.variety && (
              <>
                <dt>Variety</dt>
                <dd>{coin.variety}</dd>
              </>
            )}
            {coin.vam && (
              <>
                <dt>VAM</dt>
                <dd>{coin.vam}</dd>
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
            <dt>Stored in</dt>
            <dd>
              {coin.storage_id ? (
                <Link to={`/storage/${coin.storage_id}`}>
                  {coin.storage_name}
                  {coin.storage_position ? ` · ${coin.storage_position}` : ""}
                </Link>
              ) : (
                "—"
              )}
            </dd>
          </dl>
          )}

          <h3 className="details-sub">Purchase</h3>
          <dl className="facts">
            <dt>Paid</dt>
            <dd>
              {money(coin.price_paid)} {coin.purchase_date && <span className="muted">on {shortDate(coin.purchase_date)}</span>}
            </dd>
            <dt>From</dt>
            <dd>
              {coin.purchased_from_dealer_id ? (
                <Link to={`/dealers/${coin.purchased_from_dealer_id}`}>{coin.purchased_from}</Link>
              ) : (
                coin.purchased_from ?? "—"
              )}
            </dd>
            {coin.asking_price != null && !coin.is_sold && (
              <>
                <dt>Asking</dt>
                <dd>{money(coin.asking_price)}</dd>
              </>
            )}
            <dt>Value at purchase</dt>
            <dd>
              {coin.purchase_value?.value != null ? (
                <>
                  {money(coin.purchase_value.value)}
                  <span className="muted small dd-note">
                    {coin.purchase_value.detail}
                    {coin.purchase_value.pending && " · checking PCGS auction sales…"}
                  </span>
                </>
              ) : (
                "—"
              )}
            </dd>
          </dl>

          {coin.is_sold && (
            <>
              <h3 className="details-sub">Sale</h3>
              <dl className="facts">
                <dt>Sold</dt>
                <dd>
                  {money(coin.sale_price)} {coin.sale_date && <span className="muted">on {shortDate(coin.sale_date)}</span>}
                  {coin.sold_to && <span className="muted"> to {coin.sold_to}</span>}
                </dd>
                <dt>Profit / loss</dt>
                <dd className={pl == null ? "" : pl >= 0 ? "pos" : "neg"}>{pl == null ? "—" : money(pl)}</dd>
              </dl>
            </>
          )}
          {coin.notes && <p className="notes">{coin.notes}</p>}
        </section>
      </div>

      <ValueHistoryChart
        coinInv={coin.inventory_number}
        refreshKey={`${coin.value_estimate}-${coin.purchase_value?.value}-${coin.price_quotes.map((q) => q.id).join(",")}`}
      />

      <div className="coin-row">
        <EstimatedValueCard coin={coin} onChange={update} />
        {!coin.is_error && (
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
          {coin.details && coin.latest_cpg && (
            <p className="details-note small">
              <span className="details-badge">Details</span> This is the CPG for a problem-free {coin.latest_cpg.grade_used ?? "coin"}.
              Your coin is valued at {money(coin.details_value)}; see Estimated Value.
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
        )}
      </div>

      {coin.is_error ? null : isSet ? (
        <div className="coin-row">
          <SetMeltCard melt={coin.set_melt} />
          <AttachmentsCard inventoryNumber={coin.inventory_number} />
        </div>
      ) : (
        <>
      {SHOW_PCGS_MARKET && (
      <PcgsMarketCard
        market={coin.pcgs_market}
        cpgValue={coin.latest_cpg?.value ?? null}
        busy={pcgsBusy}
        error={pcgsError}
        onFetch={getPcgs}
      />
      )}

      <div className="coin-row">
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
        <CoinFactsCard
          facts={coin.facts}
          canFetch={Boolean(coin.grade && (coin.pcgs_number || coin.grading_service !== "RAW"))}
          busy={pcgsBusy}
          onFetch={getPcgs}
        />
      </div>

        </>
      )}

      {coin.grading_history.length > 0 && <GradingHistoryCard history={coin.grading_history} />}

      {!coin.is_sold && <CoinLinkCard inv={coin.inventory_number} />}

      {choice && (
        <CatalogPicker
          candidates={choice.candidates}
          onClose={() => setChoice(null)}
          onPick={async (c) => {
            update(await api.setPcgsNumber(inv, c.pcgs_number!, c.variety));
            setChoice(null);
            if (choice.then === "cpg") await getCpg();
            else await getPcgs();
          }}
        />
      )}

      {!isSet && (
      <div className={`coin-row${coin.is_sold ? " single" : ""}`}>
        <AttachmentsCard inventoryNumber={coin.inventory_number} />
        {!coin.is_sold && !coin.is_error && <EbayCard inv={coin.inventory_number} />}
      </div>
      )}
    </div>
  );
}

const PV_SOURCE: Record<string, string> = {
  custom: "Your value",
  cpg: "CPG",
  cpg_history: "CPG history",
  auctions: "PCGS auctions",
  paid: "Price paid",
};

const pct = (a: number, b: number) => `${a >= b ? "+" : "−"}${Math.abs(((a - b) / b) * 100).toFixed(1)}%`;

/** The numbers that matter at a glance: value now, what was paid, gain or loss, and value at purchase. */
function CoinSummary({ coin }: { coin: CoinDetail }) {
  const paid = coin.price_paid != null ? Number(coin.price_paid) : null;
  const now = coin.is_sold
    ? coin.sale_price != null
      ? Number(coin.sale_price)
      : null
    : coin.value_estimate != null
      ? Number(coin.value_estimate)
      : null;
  const gain = now != null && paid != null ? now - paid : null;
  const pv = coin.purchase_value;
  const pvNum = pv?.value != null ? Number(pv.value) : null;
  return (
    <div className="coin-summary">
      <div className="card stat">
        <div className="stat-label">{coin.is_sold ? "Sold For" : "Estimated Value"}</div>
        <div className="stat-value">{money(now)}</div>
        <div className="stat-note">
          {coin.is_sold
            ? coin.sale_date
              ? `on ${shortDate(coin.sale_date)}`
              : "Sold"
            : now == null
              ? "No price yet"
              : coin.value_source === "custom"
                ? "Your own value"
                : coin.details
                  ? <span className="info-tip" tabIndex={0} title={coin.details_basis ?? undefined}>Details coin · share of CPG ⓘ</span>
                  : `CPG${coin.latest_cpg ? ` · ${shortDate(coin.latest_cpg.confirmed_at ?? coin.latest_cpg.fetched_at)}` : ""}`}
        </div>
      </div>
      <div className="card stat">
        <div className="stat-label">Paid</div>
        <div className="stat-value">{money(paid)}</div>
        <div className="stat-note">{coin.purchase_date ? shortDate(coin.purchase_date) : "No purchase date"}</div>
      </div>
      <div className="card stat">
        <div className="stat-label">{coin.is_sold ? "Profit / Loss" : "Gain / Loss"}</div>
        <div className={`stat-value ${gain == null || Math.abs(gain) < 0.005 ? "" : gain > 0 ? "pos" : "neg"}`}>
          {gain == null ? "—" : `${Math.abs(gain) < 0.005 ? "" : gain > 0 ? "+" : "−"}${money(Math.abs(gain))}`}
        </div>
        <div className="stat-note">{gain != null && paid ? pct(now!, paid) : "Needs a price and what you paid"}</div>
      </div>
      <div className="card stat">
        <div className="stat-label">Value at Purchase</div>
        <div className="stat-value">{money(pvNum)}</div>
        <div className="stat-note">
          {pv?.pending
            ? "Checking PCGS auctions…"
            : pvNum == null
              ? "—"
              : `${PV_SOURCE[pv?.source ?? ""] ?? ""}${
                  paid && pvNum && pv?.source !== "paid" && Math.round(Math.abs(paid - pvNum)) > 0
                    ? ` · paid ${Math.abs(((paid - pvNum) / pvNum) * 100).toFixed(0)}% ${paid > pvNum ? "above" : "below"}`
                    : ""
                }`}
        </div>
      </div>
    </div>
  );
}

/** Mint & proof sets: silver content times today's spot price. */
function SetMeltCard({ melt }: { melt: CoinDetail["set_melt"] }) {
  return (
    <section className="card">
      <h2>Melt Value</h2>
      {!melt ? (
        <p className="muted small">Silver content isn't known for this set.</p>
      ) : melt.oz === 0 ? (
        <p className="muted">Clad set: no precious metal, so melt is about face value.</p>
      ) : (
        <>
          <div className="big-number">{melt.value != null ? money(melt.value) : "—"}</div>
          <p className="muted small">
            {melt.oz.toFixed(4)} oz silver{melt.spot != null && ` × ${money(melt.spot)} spot`}
            {melt.as_of && ` · ${shortDate(melt.as_of)}`}
          </p>
        </>
      )}
    </section>
  );
}

/** Every trip this coin has made to the graders: what it went as, what was expected, what it came back as. */
function GradingHistoryCard({ history }: { history: CoinDetail["grading_history"] }) {
  return (
    <section className="card">
      <h2>Grading History</h2>
      <div className="table-scroll">
        <table className="history">
          <thead>
            <tr>
              <th>Submission</th>
              <th>Sent</th>
              <th>Sent as</th>
              <th>Expected</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={`${h.submission_id}-${h.number}`}>
                <td>
                  <Link to={`/grading/${h.submission_id}`}>
                    #{h.number} {h.company_label}
                  </Link>
                  <div className="muted small">
                    {h.kind_label}
                    {h.tier_name ? ` · ${h.tier_name}` : ""}
                  </div>
                </td>
                <td>{h.date_sent ? shortDate(h.date_sent) : "—"}</td>
                <td className="small">{h.before ?? "—"}</td>
                <td className="small">{h.expected_grade ?? "—"}</td>
                <td className="small">
                  <strong>{h.outcome_label}</strong>
                  {h.after && h.after !== h.before && <div>{h.after}</div>}
                  {h.returned_on && <div className="muted">{shortDate(h.returned_on)}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** The coin's own link (its label's QR code): the public page switch, the link itself, and a new link to retire
 * labels already printed. */
function CoinLinkCard({ inv }: { inv: string }) {
  const [state, setState] = useState<CoinPublicState | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.coinPublic(inv).then(setState).catch(() => setState(null));
  }, [inv]);

  async function run(fn: () => Promise<CoinPublicState>, done?: string) {
    setBusy(true);
    setMsg(null);
    try {
      setState(await fn());
      if (done) setMsg(done);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!state) return null;
  return (
    <section className="card coin-link-card">
      <div className="row between wrap">
        <h2>Label and Public Page</h2>
        <div className="row wrap">
          <button
            className="btn small"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setMsg(null);
              try {
                if (state.queued) await api.removeQueued(inv);
                else await api.addToLabelQueue({ inventory_numbers: [inv] });
                setState({ ...state, queued: !state.queued });
                setMsg(state.queued ? "Taken out of your label queue." : "Added to your label queue.");
              } catch (e) {
                setMsg((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {state.queued ? "Remove from label queue" : "Add to label queue"}
          </button>
          <Link className="btn small" to={`/labels?coin=${encodeURIComponent(inv)}`}>
            Print label
          </Link>
        </div>
      </div>
      <label className="check public-check">
        <input type="checkbox" checked={state.public_page} disabled={busy} onChange={(e) => run(() => api.setCoinPublic(inv, e.target.checked))} />
        <span>
          Public page
          <small className="muted">
            {state.public_page
              ? "On: anyone who scans this coin's label sees its photos, grade, cert and CAC. Never prices, purchase details, storage or notes."
              : 'Off: anyone else who scans its label sees "This coin is private." You always go straight to this page.'}
          </small>
        </span>
      </label>
      {state.url ? (
        <p className="small coin-link">
          <span className="muted">Label link:</span>{" "}
          <a href={state.path ?? undefined} target="_blank" rel="noreferrer">
            {window.location.origin + state.path}
          </a>{" "}
          <button
            type="button"
            className="link-btn small"
            disabled={busy}
            onClick={() => {
              if (confirm("Make a new link? Labels you've already printed for this coin will stop working, so reprint its label afterwards."))
                run(() => api.newCoinLink(inv), "New link made. Reprint this coin's label.");
            }}
          >
            Make a new link
          </button>
        </p>
      ) : (
        <p className="small muted">This coin gets its own link the first time you print its label.</p>
      )}
      {msg && (
        <p className="small muted">
          {msg} {msg.includes("label queue") && <Link to="/labels">Go to Labels</Link>}
        </p>
      )}
    </section>
  );
}

/** More than one catalog listing fits the coin: pick the right one (its PCGS # is saved on the coin). */
function CatalogPicker({ candidates, onClose, onPick }: { candidates: CatalogCandidate[]; onClose: () => void; onPick: (c: CatalogCandidate) => Promise<void> }) {
  const usable = candidates.filter((c) => c.pcgs_number);
  const [picked, setPicked] = useState(usable.length === 1 ? usable[0].pcgs_number! : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-label="Which coin is this?">
        <div className="modal-head">
          <h2>Which Coin Is This?</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose} disabled={busy}>
            ✕
          </button>
        </div>
        <p className="muted small">
          More than one catalog listing fits this coin. Pick the right one: its PCGS coin number is saved with the coin, so
          prices come from it from now on.
        </p>
        <label className="field">
          <span>Catalog listing</span>
          <select value={picked} onChange={(e) => setPicked(e.target.value)} autoFocus>
            <option value="">Choose…</option>
            {candidates.map((c) => (
              <option key={`${c.pcgs_number ?? ""}-${c.gsid ?? c.name}`} value={c.pcgs_number ?? ""} disabled={!c.pcgs_number}>
                {c.name}
                {c.pcgs_number ? ` · PCGS #${c.pcgs_number}` : " (no PCGS #, can't be priced)"}
              </option>
            ))}
          </select>
        </label>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!picked || busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onPick(candidates.find((c) => c.pcgs_number === picked)!);
              } catch (e) {
                setError((e as Error).message);
                setBusy(false);
              }
            }}
          >
            {busy ? "Saving…" : "Use this coin"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Imported or typed-in PCGS coins weren't looked up: fetch PCGS's photos and details for the cert. */
function PcgsCheck({ inv, cert, onDone }: { inv: string; cert: string; onDone: (c: CoinDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  // PCGS lookups used up, or PCGS had no photos: open the cert on PCGS and paste a photo's address instead.
  const [paste, setPaste] = useState(false);
  return (
    <div className="pcgs-check">
      <button
        type="button"
        className="btn small"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setMsg(null);
          try {
            const r = await api.pcgsCheck(inv);
            onDone(r.coin);
            setMsg({ ok: true, text: r.message });
            setPaste(r.added === 0);
          } catch (e) {
            if (isPcgsLimit(e)) {
              setMsg({ ok: true, text: "PCGS lookups are used up for today." });
              setPaste(true);
            } else setMsg({ ok: false, text: (e as Error).message });
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Checking PCGS…" : "Check PCGS for photos"}
      </button>
      {msg ? (
        <span className={`small ${msg.ok ? "muted" : "error"}`}>{msg.text}</span>
      ) : (
        <span className="small muted">Saves PCGS's photos of this cert and fills in its PCGS #, designation and VAM.</span>
      )}
      {paste && <PcgsPhotoLink inv={inv} cert={cert} onDone={onDone} />}
    </div>
  );
}

/** Add PCGS's photos by hand: open the cert on PCGS, copy a photo's address, paste it here. */
function PcgsPhotoLink({ inv, cert, onDone }: { inv: string; cert: string; onDone: (c: CoinDetail) => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    const u = url.trim();
    if (!/^https?:\/\//i.test(u)) return setError("Paste a link that starts with https://");
    if (/pcgs\.com\/cert\//i.test(u))
      return setError("That's the cert page. On it, right-click (or long-press) a coin photo and copy the image address.");
    setBusy(true);
    setError(null);
    try {
      onDone(await api.importPhotos(inv, [u]));
      setUrl("");
    } catch (e) {
      setError(`${(e as Error).message} Copy the photo's own address (right-click or long-press it, then Copy Image Address).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pcgs-paste stack">
      <p className="small muted">
        Open{" "}
        <a href={`https://www.pcgs.com/cert/${encodeURIComponent(cert)}`} target="_blank" rel="noreferrer">
          this coin on PCGS ↗
        </a>
        , then copy a coin photo's address there and paste it below. Add the front and back one at a time.
      </p>
      <div className="row">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://images.pcgs.com/…"
          aria-label="PCGS photo link"
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
        />
        <button type="button" className="btn small" onClick={add} disabled={busy || !url.trim()}>
          {busy ? "Adding…" : "Add photo"}
        </button>
      </div>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

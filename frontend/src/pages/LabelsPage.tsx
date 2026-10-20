import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  saveFile,
  type CodeMode,
  type LabelItem,
  type LabelOptions,
  type LabelPreview,
  type LabelQueue,
  type LabelSize,
  type StorageSpotSummary,
} from "../api";
import { useApp } from "../App";
import DownloadLink from "../components/DownloadLink";
import { coinPath, money, parseMoney } from "../format";

const SIZES: { key: LabelSize; label: string; note: string }[] = [
  { key: "2x2", label: "2x2 flip inserts", note: "Raw coins · 24 a sheet, printed both sides" },
  { key: "avery5160", label: "Avery address labels", note: '1" × 2⅝", 30 a sheet (5160, 8160)' },
  { key: "thermal2x1", label: 'Thermal 2" × 1"', note: "One label at a time, for label printers" },
];
const PER_SHEET: Record<LabelSize, number> = { "2x2": 24, avery5160: 30, thermal2x1: 1 };
const FIELDS: { key: keyof LabelOptions; label: string }[] = [
  { key: "inventory", label: "Inventory #" },
  { key: "variety", label: "Variety / VAM" },
  { key: "grade", label: "Grade and service" },
  { key: "cert", label: "Cert #" },
  { key: "cac", label: "CAC" },
  { key: "storage", label: "Storage spot" },
  { key: "qr", label: "QR code" },
];

/** Print labels: the queue (or one coin, from its page), what goes on them, a preview of exactly what prints, and
 * the PDF. */
export default function LabelsPage() {
  const [params] = useSearchParams();
  const only = params.get("coin");
  const { collections } = useApp();
  const [queue, setQueue] = useState<LabelQueue | null>(null);
  const [opts, setOpts] = useState<LabelOptions | null>(null);
  const [items, setItems] = useState<LabelItem[]>([]);
  const [publicPage, setPublicPage] = useState(false);
  const [preview, setPreview] = useState<LabelPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [printed, setPrinted] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [spots, setSpots] = useState<StorageSpotSummary[]>([]);

  function take(q: LabelQueue, keepOptions = true) {
    setQueue(q);
    setItems(q.items);
    if (!keepOptions || !opts) setOpts(q.options);
  }

  useEffect(() => {
    api
      .labelQueue(only ?? undefined)
      .then((q) => take(q, false))
      .catch((e) => setError((e as Error).message));
    api.storageSpots().then(setSpots).catch(() => setSpots([]));
  }, [only]); // eslint-disable-line react-hooks/exhaustive-deps

  const needsCode = !!opts && (opts.price === "code" || opts.purchase_date === "code") && !queue?.price_code_ready;
  const job = useMemo(
    () =>
      opts && items.length
        ? {
            options: opts,
            items: items.map((i) => ({ inventory_number: i.inventory_number, asking_price: i.asking_price })),
            public_page: publicPage,
            site: window.location.origin,
          }
        : null,
    [opts, items, publicPage],
  );

  // The preview follows every change (a moment after the last one).
  const seq = useRef(0);
  useEffect(() => {
    if (!job || needsCode) {
      setPreview(null);
      return;
    }
    const n = ++seq.current;
    setPreviewing(true);
    const t = window.setTimeout(() => {
      api
        .labelPreview(job)
        .then((p) => n === seq.current && (setPreview(p), setPreviewError(null)))
        .catch((e) => n === seq.current && setPreviewError((e as Error).message))
        .finally(() => n === seq.current && setPreviewing(false));
    }, 350);
    return () => window.clearTimeout(t);
  }, [job, needsCode]);

  if (error) return <div className="page error">{error}</div>;
  if (!queue || !opts) return <div className="page muted">Loading…</div>;

  const set = <K extends keyof LabelOptions>(k: K, v: LabelOptions[K]) => {
    setOpts({ ...opts, [k]: v });
    setPrinted(null);
  };
  const sheet = PER_SHEET[opts.size];
  const usable = sheet - (sheet > 1 ? opts.start - 1 : 0);
  const pages = sheet > 1 ? Math.ceil((items.length + opts.start - 1) / sheet) : items.length;

  async function print() {
    if (!job) return;
    setPrinting(true);
    setPreviewError(null);
    try {
      saveFile(await api.printLabels(job));
      setPrinted(items.map((i) => i.inventory_number));
      if (publicPage) setItems(items.map((i) => ({ ...i, public_page: true })));
    } catch (e) {
      setPreviewError((e as Error).message);
    } finally {
      setPrinting(false);
    }
  }

  return (
    <div className="page labels-page">
      {only && items[0] ? (
        <Link to={coinPath(items[0].inventory_number)} className="btn small back-link">
          ← {items[0].title}
        </Link>
      ) : null}
      <div className="page-head">
        <div>
          <h1>{only ? "Print Label" : "Labels"}</h1>
          <p className="muted small">
            {only
              ? "One label for this coin. To print several at once, add coins to your label queue."
              : "Coins waiting for labels. Add them here or from a coin, collection or storage spot, then print them all at once."}
          </p>
        </div>
        {only && items[0] && (
          <button
            className="btn"
            onClick={async () => {
              try {
                await api.addToLabelQueue({ inventory_numbers: [items[0].inventory_number] });
                alert("Added to your label queue.");
              } catch (e) {
                alert((e as Error).message);
              }
            }}
          >
            Add to label queue instead
          </button>
        )}
      </div>

      <div className="labels-layout">
        <div className="stack">
          <section className="card">
            <h2>
              {only ? "Coin" : "Queue"} <span className="muted small">{items.length ? `${items.length} label${items.length === 1 ? "" : "s"}` : ""}</span>
            </h2>
            {!only && <AddCoins collections={collections} spots={spots} onChange={(q) => take(q)} />}
            {items.length === 0 ? (
              <p className="muted small">Nothing in the queue yet. Search above, or add a whole collection or storage spot.</p>
            ) : (
              <ul className="label-queue">
                {items.map((it) => (
                  <QueueRow
                    key={it.inventory_number}
                    it={it}
                    showAsking={opts.asking}
                    slabOn2x2={opts.size === "2x2" && !it.raw}
                    onAsking={async (v) => {
                      setItems(items.map((x) => (x.inventory_number === it.inventory_number ? { ...x, asking_price: v } : x)));
                      if (!only) {
                        try {
                          await api.setQueuedAsking(it.inventory_number, v);
                        } catch (e) {
                          alert((e as Error).message);
                        }
                      }
                    }}
                    onRemove={
                      only
                        ? undefined
                        : async () => {
                            try {
                              take(await api.removeQueued(it.inventory_number));
                            } catch (e) {
                              alert((e as Error).message);
                            }
                          }
                    }
                  />
                ))}
              </ul>
            )}
            {!only && items.length > 0 && (
              <div className="row-end">
                <button
                  type="button"
                  className="link-btn small"
                  onClick={async () => {
                    if (!confirm(`Take all ${items.length} coins out of the label queue?`)) return;
                    take(await api.clearLabelQueue());
                  }}
                >
                  Clear queue
                </button>
              </div>
            )}
          </section>

          <section className="card form-section">
            <h2>Label Size</h2>
            <div className="size-picks" role="radiogroup" aria-label="Label size">
              {SIZES.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  role="radio"
                  aria-checked={opts.size === s.key}
                  className={`size-pick ${opts.size === s.key ? "active" : ""}`}
                  onClick={() => setOpts({ ...opts, size: s.key, start: Math.min(opts.start, PER_SHEET[s.key]) })}
                >
                  <strong>{s.label}</strong>
                  <span className="small muted">{s.note}</span>
                </button>
              ))}
            </div>
            {opts.size === "2x2" && (
              <div className="square-opts">
                <span className="small muted">42.8 mm squares, sized to slide into 2x2 flips.</span>
                <label className="check">
                  <input type="checkbox" checked={opts.cut_lines} onChange={(e) => set("cut_lines", e.target.checked)} /> Print cut lines
                </label>
              </div>
            )}
            {sheet > 1 && (
              <label className="field w-auto">
                <span>Start at</span>
                <select value={opts.start} onChange={(e) => set("start", Number(e.target.value))}>
                  {Array.from({ length: sheet }, (_, i) => (
                    <option key={i} value={i + 1}>
                      {i === 0 ? "Spot 1 (a new sheet)" : `Spot ${i + 1} (skip ${i} used)`}
                    </option>
                  ))}
                </select>
                <small className="muted">
                  Spots count across, then down. {usable} free on the first sheet
                  {items.length ? ` · ${pages} page${pages === 1 ? "" : "s"}` : ""}.
                </small>
              </label>
            )}
          </section>

          <section className="card form-section">
            <h2>On The Label</h2>
            <div className="checks">
              {FIELDS.map((f) => (
                <label key={f.key}>
                  <input type="checkbox" checked={Boolean(opts[f.key])} onChange={(e) => set(f.key, e.target.checked as never)} /> {f.label}
                </label>
              ))}
              <label>
                <input type="checkbox" checked={opts.asking} onChange={(e) => set("asking", e.target.checked)} /> Asking price
              </label>
            </div>
            <div className="grid-2">
              <CodeSelect label="Price paid" value={opts.price} onChange={(v) => set("price", v)} />
              <CodeSelect label="Purchase date" value={opts.purchase_date} onChange={(v) => set("purchase_date", v)} />
            </div>
            {needsCode && (
              <div className="blocker" role="alert">
                <strong>Set up your price code first.</strong> Coded prices and dates use the price code from your
                account. <Link to="/account">Set it up in Account settings</Link>, or choose Plain or Off.
              </div>
            )}
            <label className="check public-check">
              <input type="checkbox" checked={publicPage} onChange={(e) => setPublicPage(e.target.checked)} />
              <span>
                Turn on the public page for {items.length === 1 ? "this coin" : "these coins"}
                <small className="muted">
                  {publicPage
                    ? "Anyone who scans the QR code sees its photos, grade, cert and CAC. Never prices, purchase details, storage or notes."
                    : `Off: anyone else who scans the QR code sees "This coin is private." You always go straight to your coin.${
                        items.some((i) => i.public_page) ? " (Coins whose public page is already on keep it.)" : ""
                      }`}
                </small>
              </span>
            </label>
          </section>
        </div>

        <section className="card label-preview">
          <div className="row between">
            <h2>Preview</h2>
            {previewing && <span className="small muted">Updating…</span>}
          </div>
          {needsCode ? (
            <p className="muted small">Set up your price code (or switch coded fields to Plain or Off) to see the preview.</p>
          ) : !items.length ? (
            <p className="muted small">Add coins to see their labels.</p>
          ) : preview ? (
            <>
              <div className={`preview-labels size-${opts.size}`}>
                {preview.labels.map((svg, i) => (
                  <figure key={i}>
                    <img src={svgUrl(svg)} alt={preview.two_sided ? `${i % 2 ? "Back" : "Front"} of label ${Math.floor(i / 2) + 1}` : `Label ${i + 1}`} />
                    {preview.two_sided && <figcaption className="small muted">{i % 2 ? "Back" : "Front"}</figcaption>}
                  </figure>
                ))}
              </div>
              <p className="small muted">
                {(() => {
                  const shown = preview.two_sided ? preview.labels.length / 2 : preview.labels.length;
                  return preview.label_count > shown
                    ? `The first ${shown} of ${preview.label_count} labels, shown larger than life.`
                    : `${preview.label_count === 1 ? "Your label" : `All ${preview.label_count} labels`}, shown larger than life.`;
                })()}
                {preview.two_sided && " The circle on the front shows where the coin sits; it doesn't print."}
              </p>
              {preview.pages.length > 0 && (
                <>
                  <h3 className="details-sub">Where They Print</h3>
                  <div className="preview-pages">
                    {preview.pages.map((svg, i) => (
                      <figure key={i}>
                        <img src={svgUrl(svg)} alt={preview.two_sided ? (i ? "Backs" : "Fronts") : `Page ${i + 1}`} />
                        {preview.two_sided && <figcaption className="small muted">{i ? "Backs (other side)" : "Fronts"}</figcaption>}
                      </figure>
                    ))}
                  </div>
                  <p className="small muted">
                    {preview.page_count} {preview.two_sided ? "sheet" : "page"}
                    {preview.page_count === 1 ? "" : "s"}
                    {preview.two_sided ? " (fronts and backs)" : ""}
                    {!preview.two_sided && preview.page_count > preview.pages.length ? `, showing the first ${preview.pages.length}` : ""}.
                  </p>
                </>
              )}
              {preview.warnings.map((w) => (
                <p key={w} className="small warn">
                  {w}
                </p>
              ))}
            </>
          ) : null}
          {previewError && <p className="error small">{previewError}</p>}
          <div className="row-end">
            <button className="btn btn-primary" disabled={!job || needsCode || printing} onClick={print}>
              {printing ? "Preparing…" : items.length === 1 ? "Print label" : `Print ${items.length} labels`}
            </button>
          </div>
          <p className="small muted">
            {opts.size === "thermal2x1"
              ? 'Downloads a PDF of 2" × 1" pages. Print it to your label printer at Actual size (100%).'
              : opts.size === "2x2"
                ? "Downloads a PDF: a page of fronts, then a page of backs. Print double-sided (flip on long edge) at Actual size (100%). No double-sided printing? Print the fronts, put the sheet back in to print on its other side, then print the backs."
                : "Downloads a PDF. Print it at Actual size (100%), not Fit to page, so the labels line up."}
          </p>
          {opts.size === "2x2" && (
            <p className="small">
              <DownloadLink href={api.alignmentTestUrl()}>Print an alignment test</DownloadLink>{" "}
              <span className="muted">first: hold it up to a light and each back's cross should sit on its front's.</span>
            </p>
          )}
          {printed && (
            <div className="printed-note">
              <p className="small ok">Labels downloaded.</p>
              {!only && (
                <button
                  className="btn small"
                  onClick={async () => {
                    take(await api.clearLabelQueue(printed));
                    setPrinted(null);
                  }}
                >
                  Take these out of the queue
                </button>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const svgUrl = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

function CodeSelect({ label, value, onChange }: { label: string; value: CodeMode; onChange: (v: CodeMode) => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as CodeMode)}>
        <option value="off">Off</option>
        <option value="plain">Plain</option>
        <option value="code">Coded (your price code)</option>
      </select>
    </label>
  );
}

function QueueRow({ it, showAsking, slabOn2x2, onAsking, onRemove }: { it: LabelItem; showAsking: boolean; slabOn2x2: boolean; onAsking: (v: string | null) => void; onRemove?: () => void }) {
  const [asking, setAsking] = useState(it.asking_price ?? "");
  const [bad, setBad] = useState(false);
  useEffect(() => setAsking(it.asking_price ?? ""), [it.asking_price]);
  return (
    <li className={slabOn2x2 ? "skipped" : ""}>
      <div className="label-queue-main">
        <Link to={coinPath(it.inventory_number)}>{it.title}</Link>
        <span className="small muted">
          {it.inventory_number} · {it.grade}
          {it.price_paid ? ` · paid ${money(it.price_paid)}` : ""}
          {it.public_page && <span className="tag">Public page on</span>}
          {slabOn2x2 && <span className="tag">Slab: not on 2x2s</span>}
        </span>
      </div>
      {showAsking && (
        <label className="asking">
          <span className="small muted">Asking</span>
          <input
            type="text"
            inputMode="decimal"
            value={asking}
            placeholder="None"
            aria-label={`Asking price for ${it.inventory_number}`}
            aria-invalid={bad}
            onChange={(e) => {
              setAsking(e.target.value);
              setBad(false);
            }}
            onBlur={() => {
              const r = parseMoney(asking || null);
              if ("error" in r) return setBad(true);
              setAsking(r.value ?? "");
              if ((r.value ?? null) !== (it.asking_price ?? null)) onAsking(r.value);
            }}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        </label>
      )}
      {onRemove && (
        <button type="button" className="link-btn small icon-x" aria-label={`Take ${it.inventory_number} out of the queue`} onClick={onRemove}>
          ✕
        </button>
      )}
    </li>
  );
}

type Hit = { inventory_number: string; label: string; sold: boolean };

function AddCoins({ collections, spots, onChange }: { collections: { id: number; name: string }[]; spots: StorageSpotSummary[]; onChange: (q: LabelQueue) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const term = q.trim();
    if (!term) return setHits([]);
    let live = true;
    const t = window.setTimeout(() => {
      api
        .searchCoins(term, 8)
        .then((r) =>
          live &&
          setHits(
            r.map((h) => ({
              inventory_number: h.coin.inventory_number,
              label: `${h.coin.year}${h.coin.mint_mark !== "P" ? `-${h.coin.mint_mark}` : ""} ${h.type_name} · ${h.collection_name}`,
              sold: h.coin.is_sold,
            })),
          ),
        )
        .catch(() => live && setHits([]));
    }, 150);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [q]);

  async function add(b: { inventory_numbers?: string[]; collection_id?: number; storage_id?: number }) {
    setBusy(true);
    setError(null);
    try {
      onChange(await api.addToLabelQueue(b));
      setQ("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack add-coins">
      <div className="coin-search">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Add a coin: inventory #, cert, 1881-S, Morgan…" aria-label="Search your coins to add" maxLength={100} />
        {hits.length > 0 && (
          <ul className="coin-search-hits">
            {hits.map((h) => (
              <li key={h.inventory_number}>
                <span>
                  <strong>{h.inventory_number}</strong> {h.label}
                </span>
                <button type="button" className="btn small" disabled={busy || h.sold} onClick={() => add({ inventory_numbers: [h.inventory_number] })}>
                  {h.sold ? "Sold" : "+ Add"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="row wrap">
        <select
          value=""
          disabled={busy || !collections.length}
          onChange={(e) => e.target.value && add({ collection_id: Number(e.target.value) })}
          aria-label="Add a whole collection"
        >
          <option value="">Add a collection…</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value=""
          disabled={busy || !spots.length}
          onChange={(e) => e.target.value && add({ storage_id: Number(e.target.value) })}
          aria-label="Add everything in a storage spot"
        >
          <option value="">Add a storage spot…</option>
          {spots.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

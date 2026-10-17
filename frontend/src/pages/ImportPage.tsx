import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useSearchParams } from "react-router-dom";
import { api, type ImportPreview, type ImportResult, type ImportRow } from "../api";
import { useApp } from "../App";
import { collectionPath, money } from "../format";

type Mode = "file" | "certs";

const TEMPLATE_HEADERS = [
  "Type", "Date", "Grade", "Grading service", "Cert #", "CAC sticker", "Variety", "VAM", "Collector slab", "Toning",
  "Price paid", "Date purchased", "Purchased from", "Notes",
];
const TEMPLATE_EXAMPLE = [
  "Morgan Dollar", "1881-S", "MS65+ DMPL", "PCGS", "12345678", "Green", "", "VAM-3", "Rattler", "Obverse",
  "250.00", "2025-03-15", "Heritage", "",
];

const rowKey = (r: ImportRow) => `${r.sheet}-${r.row}`;

function downloadTemplate() {
  const csv = [TEMPLATE_HEADERS, TEMPLATE_EXAMPLE].map((r) => r.map((v) => (v.includes(",") ? `"${v}"` : v)).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv + "\n"], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "TrackMyCoins_import_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

/** Bulk import from a spreadsheet (CSV / Excel, including our own export) or a pasted list of PCGS certs. */
export default function ImportPage() {
  const { collections, coinTypes, refresh } = useApp();
  const [search] = useSearchParams();
  const typeSets = useMemo(() => new Set(coinTypes.filter((t) => t.is_type_set).map((t) => t.id)), [coinTypes]);
  const targets = collections.filter((c) => !typeSets.has(c.coin_type_id));

  const fileInput = useRef<HTMLInputElement>(null);
  // null: sort each coin into the collection for its series (the default)
  const [collectionId, setCollectionId] = useState<number | null>(Number(search.get("collection")) || null);
  const [mode, setMode] = useState<Mode>("file");
  const [certs, setCerts] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [importPhotos, setImportPhotos] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);

  function reset() {
    setPreview(null);
    setResult(null);
    setSkip(new Set());
    setError(null);
  }

  async function run(fn: () => Promise<ImportPreview>) {
    reset();
    setBusy(true);
    try {
      setPreview(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const ready = preview ? preview.rows.filter((r) => r.errors.length === 0 && !skip.has(rowKey(r))) : [];
  const hasPhotos = preview?.rows.some((r) => r.photo_urls.length > 0) ?? false;

  async function commit() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      // Rows the user unticked go back marked as skipped.
      const rows: ImportRow[] = preview.rows.map((r) => (skip.has(rowKey(r)) ? { ...r, errors: [...r.errors, "Skipped"] } : r));
      setResult(await api.importCommit(collectionId, rows, importPhotos));
      setPreview(null);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page import-page">
      <div className="page-head">
        <div>
          <h1>Import Coins</h1>
          <p className="muted">Add many coins at once from a spreadsheet or a list of PCGS cert numbers.</p>
        </div>
      </div>

      <section className="card form-section">
        <label className="field">
          <span>Import into</span>
          <select
            value={collectionId ?? "auto"}
            onChange={(e) => {
              setCollectionId(e.target.value === "auto" ? null : Number(e.target.value));
              reset();
            }}
          >
            <option value="auto">Sort by coin type (automatic)</option>
            {targets.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.collection_type_label})
              </option>
            ))}
          </select>
        </label>
        {collectionId === null && (
          <p className="muted small">
            Each coin goes into your first collection for its series (proofs into a Proof collection). If you don't
            have one yet, it's created. The series comes from a Type column (like Morgan Dollar), words after the
            date (like 1881-S Morgan Dollar), the PCGS number, or a TrackMyCoins inventory number.
          </p>
        )}

        <div className="segmented mode-switch" role="tablist">
          <button type="button" className={`seg ${mode === "file" ? "active" : ""}`} onClick={() => { setMode("file"); reset(); }}>
            Spreadsheet
          </button>
          <button type="button" className={`seg ${mode === "certs" ? "active" : ""}`} onClick={() => { setMode("certs"); reset(); }}>
            PCGS cert numbers
          </button>
        </div>

        {mode === "file" ? (
          <div className="stack">
            <p className="muted small">
              A CSV or Excel file with one coin per row and column headings in the first row. A TrackMyCoins export
              works as-is, including its Sold sheet. Columns can include Type (like Morgan Dollar), Date (like 1881-S), Grade (like MS65+ DMPL or
              Raw AU55), Grading service, Cert #, CAC sticker, Variety, VAM, Collector slab, Toning, Price paid, Date
              purchased, Purchased from and Notes.
            </p>
            <div className="row">
              {/* A real button (a hidden input inside a label can't be reached by keyboard) */}
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => fileInput.current?.click()}
              >
                {busy ? "Reading…" : "Choose file"}
              </button>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) run(() => api.importPreview(collectionId, f));
                }}
              />
              <button type="button" className="btn" onClick={downloadTemplate}>
                Download template
              </button>
            </div>
          </div>
        ) : (
          <div className="stack">
            <p className="muted small">
              Paste PCGS cert numbers, one per line or separated by commas (up to 50 at a time). Each is looked up with
              PCGS for its date, grade, designation and photos. PCGS allows 1,000 lookups a day.
            </p>
            <textarea rows={6} value={certs} onChange={(e) => setCerts(e.target.value)} placeholder={"12345678\n23456789"} />
            <div className="row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !certs.trim()}
                onClick={() => run(() => api.importCerts(collectionId, certs))}
              >
                {busy ? "Looking up…" : "Look up certs"}
              </button>
            </div>
          </div>
        )}
        {error && <p className="error">{error}</p>}
      </section>

      {preview && (
        <section className="card form-section">
          <div className="section-head">
            <h2>Check Before Importing</h2>
            <span className="small muted">
              {preview.ok_count} ready{preview.error_count ? ` · ${preview.error_count} with problems (won't be imported)` : ""}
            </span>
          </div>
          <Destinations rows={preview.rows.filter((r) => r.errors.length === 0 && !skip.has(rowKey(r)))} />
          <ul className="import-list">
            {preview.rows.map((r) => {
              const ok = r.errors.length === 0;
              return (
                <li key={rowKey(r)} className={`import-row ${ok ? "" : "bad"}`}>
                  <label className="import-pick">
                    <input
                      type="checkbox"
                      disabled={!ok}
                      checked={ok && !skip.has(rowKey(r))}
                      onChange={(e) =>
                        setSkip((cur) => {
                          const next = new Set(cur);
                          if (e.target.checked) next.delete(rowKey(r));
                          else next.add(rowKey(r));
                          return next;
                        })
                      }
                      aria-label={`Import row ${r.row}`}
                    />
                  </label>
                  <div className="import-main">
                    <strong>{r.description}</strong>
                    <span className="small muted">
                      {r.sheet && r.sheet !== "CSV" ? `${r.sheet} sheet, ` : ""}
                      {mode === "file" ? `row ${r.row}` : `#${r.row}`}
                      {r.fields.price_paid ? ` · paid ${money(r.fields.price_paid as string)}` : ""}
                      {r.fields.sale_price ? ` · sold ${money(r.fields.sale_price as string)}` : ""}
                      {r.photo_urls.length ? ` · ${r.photo_urls.length} photo${r.photo_urls.length === 1 ? "" : "s"}` : ""}
                    </span>
                    {ok && r.target && collectionId === null && (
                      <span className="small import-target">
                        → {r.target}
                        {r.target_new && <span className="tag">New</span>}
                      </span>
                    )}
                    {r.errors.map((e) => (
                      <span key={e} className="small error">
                        {e}
                      </span>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
          {hasPhotos && (
            <label className="checks">
              <span>
                <input type="checkbox" checked={importPhotos} onChange={(e) => setImportPhotos(e.target.checked)} /> Also
                save PCGS's photos with each coin
              </span>
            </label>
          )}
          <div className="row-end">
            <button type="button" className="btn" onClick={reset}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" disabled={busy || ready.length === 0} onClick={commit}>
              {busy ? "Importing…" : `Import ${ready.length} coin${ready.length === 1 ? "" : "s"}`}
            </button>
          </div>
        </section>
      )}

      {result && <ImportReport result={result} onClose={reset} />}
    </div>
  );
}

/** Where the ticked rows will go: "Morgans (3) · Peace Dollar Collection 1 (new, 2)". */
function Destinations({ rows }: { rows: ImportRow[] }) {
  const groups = new Map<string, { count: number; isNew: boolean }>();
  for (const r of rows) {
    if (!r.target) continue;
    const g = groups.get(r.target) ?? { count: 0, isNew: Boolean(r.target_new) };
    g.count += 1;
    groups.set(r.target, g);
  }
  if (groups.size < 2 && ![...groups.values()].some((g) => g.isNew)) return null;
  return (
    <div className="import-dest small">
      <span className="muted">Going into:</span>
      {[...groups].map(([name, g]) => (
        <span key={name} className="import-dest-item">
          {name} ({g.isNew ? "new, " : ""}
          {g.count})
        </span>
      ))}
    </div>
  );
}

/** After an import: how many went in (and where), and every row that didn't with the reason. */
function ImportReport({ result, onClose }: { result: ImportResult; onClose: () => void }) {
  const { collections } = useApp();
  const rejected = result.skipped.filter((s) => !s.errors.includes("Skipped"));
  const unticked = result.skipped.length - rejected.length;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const n = result.created.length;
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal import-report" role="dialog" aria-label="Import results" onClick={(e) => e.stopPropagation()}>
        <h2>Import Complete</h2>
        <div className="import-counts">
          <div className="import-count ok">
            <strong>{n}</strong>
            <span>accepted</span>
          </div>
          <div className={`import-count ${rejected.length ? "bad" : ""}`}>
            <strong>{rejected.length}</strong>
            <span>rejected</span>
          </div>
        </div>
        {unticked > 0 && (
          <p className="muted small">
            {unticked} row{unticked === 1 ? "" : "s"} you unticked {unticked === 1 ? "was" : "were"} left out.
          </p>
        )}

        {result.collections.length > 0 && (
          <>
            <h3>Added To</h3>
            <ul className="import-report-cols">
              {result.collections.map((c) => {
                const col = collections.find((x) => x.id === c.id);
                return (
                  <li key={c.id}>
                    {col ? (
                      <Link to={collectionPath(col)} onClick={onClose}>
                        {c.name}
                      </Link>
                    ) : (
                      c.name
                    )}
                    {c.new && <span className="tag">New</span>}
                    <span className="muted">
                      {c.count} coin{c.count === 1 ? "" : "s"}
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}

        {rejected.length > 0 && (
          <>
            <h3>Rejected</h3>
            <ul className="import-report-bad">
              {rejected.map((s) => (
                <li key={`${s.sheet}-${s.row}`}>
                  <div>
                    <strong>{s.description || "Unreadable row"}</strong>
                    <span className="muted small">
                      {" "}
                      · {s.sheet && s.sheet !== "CSV" ? `${s.sheet} sheet, ` : ""}row {s.row}
                    </span>
                  </div>
                  {s.errors.map((e) => (
                    <div key={e} className="small error">
                      {e}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
            <p className="muted small">Fix these rows in your file and import it again; coins already added are flagged as duplicates.</p>
          </>
        )}

        <div className="row-end">
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

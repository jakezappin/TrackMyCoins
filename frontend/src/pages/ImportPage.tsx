import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type ImportPreview, type ImportRow } from "../api";
import { useApp } from "../App";
import { collectionPath, money } from "../format";

type Mode = "file" | "certs";

const TEMPLATE_HEADERS = [
  "Date", "Grade", "Grading service", "Cert #", "CAC sticker", "Variety", "VAM", "Collector slab", "Toning",
  "Price paid", "Date purchased", "Purchased from", "Notes",
];
const TEMPLATE_EXAMPLE = [
  "1881-S", "MS65+ DMPL", "PCGS", "12345678", "Green", "", "VAM-3", "Rattler", "Obverse",
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
  const [collectionId, setCollectionId] = useState<number | null>(Number(search.get("collection")) || null);
  const [mode, setMode] = useState<Mode>("file");
  const [certs, setCerts] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [skip, setSkip] = useState<Set<string>>(new Set());
  const [importPhotos, setImportPhotos] = useState(true);
  const [result, setResult] = useState<{ created: string[]; skipped: { row: number; description: string; errors: string[] }[] } | null>(null);

  useEffect(() => {
    if (collectionId === null && targets.length) setCollectionId(targets[0].id);
  }, [targets, collectionId]);
  const collection = collections.find((c) => c.id === collectionId);

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
    if (!preview || !collectionId) return;
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
            value={collectionId ?? ""}
            onChange={(e) => {
              setCollectionId(Number(e.target.value));
              reset();
            }}
          >
            {targets.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.collection_type_label})
              </option>
            ))}
          </select>
        </label>
        {targets.length === 0 && <p className="muted small">Create a collection first.</p>}

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
              works as-is, including its Sold sheet. Columns can include Date (like 1881-S), Grade (like MS65+ DMPL or
              Raw AU55), Grading service, Cert #, CAC sticker, Variety, VAM, Collector slab, Toning, Price paid, Date
              purchased, Purchased from and Notes.
            </p>
            <div className="row">
              {/* A real button (a hidden input inside a label can't be reached by keyboard) */}
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !collectionId}
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
                  if (f && collectionId) run(() => api.importPreview(collectionId, f));
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
                disabled={busy || !certs.trim() || !collectionId}
                onClick={() => collectionId && run(() => api.importCerts(collectionId, certs))}
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

      {result && collection && (
        <section className="card form-section">
          <h2>
            Imported {result.created.length} Coin{result.created.length === 1 ? "" : "s"}
          </h2>
          {result.created.length > 0 && (
            <p className="small muted">
              {result.created[0]}
              {result.created.length > 1 ? ` to ${result.created[result.created.length - 1]}` : ""}
            </p>
          )}
          {result.skipped.length > 0 && (
            <p className="small muted">
              {result.skipped.length} row{result.skipped.length === 1 ? " was" : "s were"} skipped.
            </p>
          )}
          <div className="row">
            <Link className="btn btn-primary" to={collectionPath(collection)}>
              Go to {collection.name}
            </Link>
            <button type="button" className="btn" onClick={reset}>
              Import more
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type BullionImportRow } from "../api";
import { ozLabel, purityLabel } from "../bullionFormat";
import { money } from "../format";

/** Import bullion from a CSV / Excel file into a collection: pick a file, check the rows, import. */
export default function BullionImportDialog({ collectionId, onClose, onDone }: { collectionId: number; onClose: () => void; onDone: () => void }) {
  const file = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<BullionImportRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ created: string[]; skipped: { row: number; description: string; errors: string[] }[] } | null>(null);
  const ok = rows?.filter((r) => r.errors.length === 0) ?? [];

  async function preview(f: File) {
    setBusy(true);
    setError(null);
    try {
      setRows((await api.bullionImportPreview(collectionId, f)).rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!rows) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.bullionImportCommit(collectionId, rows));
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal import-report" role="dialog" aria-label="Import bullion" onClick={(e) => e.stopPropagation()}>
        <h2>Import Bullion</h2>
        {result ? (
          <>
            <div className="import-counts">
              <div className="import-count ok">
                <strong>{result.created.length}</strong>
                <span>imported</span>
              </div>
              <div className={`import-count ${result.skipped.length ? "bad" : ""}`}>
                <strong>{result.skipped.length}</strong>
                <span>rejected</span>
              </div>
            </div>
            {result.skipped.length > 0 && (
              <ul className="import-report-bad">
                {result.skipped.map((s) => (
                  <li key={s.row}>
                    <strong>{s.description || "Unreadable row"}</strong> <span className="muted small">row {s.row}</span>
                    {s.errors.map((e) => (
                      <div key={e} className="small error">
                        {e}
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            )}
            <div className="row-end">
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="muted small">
              A CSV or Excel file, one item per row, headings in the first row: Description, Packaging, Quantity, Weight,
              Unit (ozt, grams, kilos), Purity (.999, 90%, 22k), Face value (junk silver), Price paid, Date purchased,
              Purchased from, Notes. A TrackMyCoins bullion export works as is.
            </p>
            <div className="row">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => file.current?.click()}>
                {busy && !rows ? "Reading…" : rows ? "Choose another file" : "Choose file"}
              </button>
              <a className="btn" href={api.bullionTemplateUrl} download>
                Download template
              </a>
              <input
                ref={file}
                type="file"
                hidden
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) preview(f);
                }}
              />
            </div>
            {rows && (
              <>
                <p className="small">
                  <strong>{ok.length}</strong> ready{rows.length - ok.length ? ` · ${rows.length - ok.length} with problems (won't be imported)` : ""}
                </p>
                <ul className="import-list">
                  {rows.map((r) => (
                    <li key={`${r.sheet}-${r.row}`} className={`import-row ${r.errors.length ? "bad" : ""}`}>
                      <div className="import-main">
                        <strong>{r.fields.description || "No description"}</strong>
                        <span className="small muted">
                          row {r.row}
                          {r.fields.oz && ` · ${ozLabel(r.fields.oz)} pure`}
                          {r.fields.purity && ` · ${purityLabel(r.fields.purity)}`}
                          {r.fields.price_paid && ` · paid ${money(r.fields.price_paid)}`}
                        </span>
                        {r.errors.map((e) => (
                          <span key={e} className="small error">
                            {e}
                          </span>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {error && <p className="error small">{error}</p>}
            <div className="row-end">
              <button className="btn" onClick={onClose}>
                Cancel
              </button>
              <button className="btn btn-primary" disabled={busy || ok.length === 0} onClick={commit}>
                {busy && rows ? "Importing…" : `Import ${ok.length} item${ok.length === 1 ? "" : "s"}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}

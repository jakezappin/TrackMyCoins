import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { api, type ExportColumn } from "../api";

const GROUPS: [string, string[]][] = [
  ["Coin", ["Inventory #", "Date", "Year", "Mint", "Variety", "VAM", "PCGS #"]],
  ["Grading & Holder", ["Grading service", "Cert #", "Grade", "CAC", "CAC sticker", "Collector slab", "Packaging", "Toning"]],
  ["Purchase", ["Price paid", "Date purchased", "Purchased from"]],
  ["Value", ["CPG value", "CPG as of", "Toner premium", "Holder premium", "Value source", "Estimated value"]],
  ["Sale (Sold Sheet)", ["Sale price", "Sale date", "Sold to", "Profit / loss"]],
];
const STORE_KEY = "export-columns";

function loadSaved(): string[] | null {
  try {
    const v = JSON.parse(localStorage.getItem(STORE_KEY) ?? "null");
    return Array.isArray(v) ? v : null;
  } catch {
    return null;
  }
}

/** Pick which columns go into the Excel export, then download it. */
export default function ExportDialog({ collectionId, onClose }: { collectionId: number; onClose: () => void }) {
  const [columns, setColumns] = useState<ExportColumn[] | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .exportColumns()
      .then((cols) => {
        setColumns(cols);
        const names = cols.map((c) => c.name);
        const saved = loadSaved()?.filter((n) => names.includes(n));
        setChosen(new Set(saved && saved.length ? saved : names));
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const groups = useMemo(() => {
    if (!columns) return [];
    const known = new Set(GROUPS.flatMap(([, n]) => n));
    const names = columns.map((c) => c.name);
    const out = GROUPS.map(([title, n]) => [title, n.filter((x) => names.includes(x))] as [string, string[]]);
    const other = names.filter((n) => !known.has(n));
    if (other.length) out.push(["Other", other]);
    return out.filter(([, n]) => n.length);
  }, [columns]);

  const toggle = (names: string[], on: boolean) =>
    setChosen((cur) => {
      const next = new Set(cur);
      names.forEach((n) => (on ? next.add(n) : next.delete(n)));
      return next;
    });

  function download() {
    if (!columns) return;
    const ordered = columns.map((c) => c.name).filter((n) => chosen.has(n));
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(ordered));
    } catch {
      // Remembering the choice is only a convenience.
    }
    const qs = ordered.length === columns.length ? "" : "?" + ordered.map((n) => `columns=${encodeURIComponent(n)}`).join("&");
    const a = document.createElement("a");
    a.href = api.exportUrl(collectionId) + qs;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
    onClose();
  }

  const all = columns?.map((c) => c.name) ?? [];
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal export-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Export to Excel">
        <h2>Export To Excel</h2>
        <p className="muted small">
          Choose the columns for the Coins and Sold sheets. The Summary and Checklist sheets are always included.
        </p>
        {error && <p className="error small">{error}</p>}
        {!columns && !error && <p className="muted small">Loading…</p>}
        {columns && (
          <>
            <div className="row export-quick">
              <button type="button" className="link-btn small" onClick={() => toggle(all, true)}>
                Select all
              </button>
              <button type="button" className="link-btn small" onClick={() => toggle(all, false)}>
                Clear all
              </button>
              <span className="small muted">
                {chosen.size} of {all.length} columns
              </span>
            </div>
            <div className="export-groups">
              {groups.map(([title, names]) => {
                const on = names.filter((n) => chosen.has(n)).length;
                return (
                  <fieldset key={title} className="export-group">
                    <legend>
                      <label>
                        <input
                          type="checkbox"
                          checked={on === names.length}
                          ref={(el) => {
                            if (el) el.indeterminate = on > 0 && on < names.length;
                          }}
                          onChange={(e) => toggle(names, e.target.checked)}
                        />{" "}
                        {title}
                      </label>
                    </legend>
                    {names.map((n) => (
                      <label key={n} className="export-col">
                        <input type="checkbox" checked={chosen.has(n)} onChange={(e) => toggle([n], e.target.checked)} /> {n}
                      </label>
                    ))}
                  </fieldset>
                );
              })}
            </div>
          </>
        )}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" disabled={!columns || chosen.size === 0} onClick={download}>
            Download
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

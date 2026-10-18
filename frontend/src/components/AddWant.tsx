import { useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { parseMoney } from "../format";

const PREFIXES = ["MS", "PR", "SP", "AU", "XF", "VF", "F", "VG", "G", "AG"];

/** "+ Want" button: put a date/mint (and variety) on the want list with a target grade and max price. */
export default function AddWant(props: {
  collectionId: number;
  year: number;
  mintMark: string;
  variety: string | null;
  grade?: number | null;
  gradePrefix?: string | null;
  maxPrice?: string | null;
  label: string;
  /** Mint & proof sets: no target grade */
  noGrade?: boolean;
  /** Already on the want list */
  already?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [prefix, setPrefix] = useState(props.gradePrefix ?? "MS");
  const [grade, setGrade] = useState(props.grade ? String(props.grade) : "");
  const [max, setMax] = useState(props.maxPrice ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const price = parseMoney(max);
    if ("error" in price) {
      setError(`Max price ${price.error}.`);
      return;
    }
    if (grade && !props.noGrade && (!/^\d+$/.test(grade.trim()) || Number(grade) < 1 || Number(grade) > 70)) {
      setError("Target grade must be a whole number from 1 to 70.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.addWant({
        collection_id: props.collectionId,
        year: props.year,
        mint_mark: props.mintMark,
        variety: props.variety,
        grade_prefix: grade && !props.noGrade ? prefix : null,
        grade: grade && !props.noGrade ? Number(grade) : null,
        max_price: price.value,
      });
      setDone(true);
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (done || props.already) return <span className="small muted want-done">✓ On want list</span>;
  return (
    <>
      <button type="button" className="btn small" onClick={() => setOpen(true)} aria-label={`Add ${props.label} to want list`}>
        + Want
      </button>
      {open &&
        createPortal(
          <div className="modal-backdrop" onClick={() => !busy && setOpen(false)}>
            <div className="modal" role="dialog" aria-label="Add to want list" onClick={(e) => e.stopPropagation()}>
              <h2>Add To Want List</h2>
              <p className="strong">{props.label}</p>
              <div className="row">
                {!props.noGrade && (
                <label className="field">
                  <span>Target grade</span>
                  <div className="row tight">
                    <select value={prefix} onChange={(e) => setPrefix(e.target.value)} className="w-auto">
                      {PREFIXES.map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                    <input type="number" min={1} max={70} step={1} value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="65" />
                  </div>
                </label>
                )}
                <label className="field">
                  <span>Max price (optional)</span>
                  <input type="text" inputMode="decimal" value={max} onChange={(e) => setMax(e.target.value)} placeholder="0.00" />
                </label>
              </div>
              {error && <p className="error small">{error}</p>}
              <div className="row-end">
                <button type="button" className="btn" onClick={() => setOpen(false)}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary" disabled={busy} onClick={save}>
                  {busy ? "Adding…" : "Add"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

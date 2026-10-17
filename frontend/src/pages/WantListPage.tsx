import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { api, type Finish, type WantIn, type WantItem } from "../api";
import { useApp } from "../App";
import { coinPath, gradeLabel, money, parseMoney } from "../format";

const PREFIXES = ["MS", "PR", "SP", "AU", "XF", "VF", "F", "VG", "G", "AG"];

/** Coins the user is looking for: target grade, max price, CPG at that grade, and whether they already own one. */
export default function WantListPage() {
  const [wants, setWants] = useState<WantItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<WantItem | "new" | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => api.wants().then(setWants).catch((e) => setError((e as Error).message));
  useEffect(() => {
    load();
  }, []);

  async function run(id: number, fn: () => Promise<void>) {
    if (busy !== null) return;
    setBusy(id);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const price = (w: WantItem) =>
    run(w.id, async () => {
      const updated = await api.priceWant(w.id);
      setWants((cur) => cur?.map((x) => (x.id === w.id ? updated : x)) ?? null);
    });
  const remove = (w: WantItem) =>
    confirm(`Remove ${w.label} from your want list?`) &&
    run(w.id, async () => {
      await api.deleteWant(w.id);
      setWants((cur) => cur?.filter((x) => x.id !== w.id) ?? null);
    });

  return (
    <div className="page want-page">
      <div className="page-head">
        <div>
          <h1>Want List</h1>
          <p className="muted">Coins you're looking for, with CPG at your target grade.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>
          + Add a coin
        </button>
      </div>
      {error && (
        <p className="error banner" role="alert">
          {error}
        </p>
      )}
      {!wants ? (
        <p className="muted">Loading…</p>
      ) : wants.length === 0 ? (
        <div className="card empty-state">
          <p className="muted">
            Nothing on your want list yet. Add coins here, or use <strong>+ Want</strong> next to a missing date on a
            collection's Collection Status page or in the Upgrade Finder.
          </p>
        </div>
      ) : (
        <section className="card table-card">
          <ul className="want-list">
            {wants.map((w) => (
              <li key={w.id} className={`want-row ${w.owned?.meets_target ? "got" : ""}`}>
                <div className="want-main">
                  <strong>{w.label}</strong>
                  <span className="small muted">
                    {w.target_label ? `Target ${w.target_label}` : "Any grade"}
                    {w.max_price ? ` · up to ${money(w.max_price)}` : ""}
                    {w.collection_name ? ` · for ${w.collection_name}` : ""}
                  </span>
                  {w.notes && <span className="small muted">{w.notes}</span>}
                  {w.owned && (
                    <span className={`small ${w.owned.meets_target ? "pos" : "muted"}`}>
                      {w.owned.meets_target ? "✓ Got it: " : "You have "}
                      <Link to={coinPath(w.owned.inventory_number)}>
                        {w.owned.inventory_number} ({gradeLabel(w.owned)})
                      </Link>
                      {!w.owned.meets_target && w.grade ? ", below your target" : ""}
                    </span>
                  )}
                </div>
                <div className="want-price">
                  {w.cpg ? (
                    <>
                      <span className="small muted">CPG {w.target_label}</span>
                      <strong>{money(w.cpg)}</strong>
                      {w.max_price && Number(w.cpg) > Number(w.max_price) && (
                        <span className="small warn">above your max</span>
                      )}
                    </>
                  ) : w.priceable ? (
                    <button type="button" className="btn small" disabled={busy !== null} onClick={() => price(w)}>
                      {busy === w.id ? "Getting…" : "Get price"}
                    </button>
                  ) : (
                    <span className="small muted">{w.grade ? "No CPG listed" : "Set a grade to see CPG"}</span>
                  )}
                </div>
                <div className="want-actions">
                  <button type="button" className="btn small" onClick={() => setEditing(w)} disabled={busy !== null}>
                    Edit
                  </button>
                  <button type="button" className="btn small danger-outline" onClick={() => remove(w)} disabled={busy !== null}>
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
      {editing && (
        <WantForm
          want={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function WantForm({ want, onClose, onSaved }: { want: WantItem | null; onClose: () => void; onSaved: () => void }) {
  const { coinTypes, collections } = useApp();
  const series = useMemo(() => coinTypes.filter((t) => !t.is_type_set), [coinTypes]);
  // Start on a series the user collects rather than the first one alphabetically.
  const collected = collections.find((c) => series.some((t) => t.id === c.coin_type_id));
  const [typeId, setTypeId] = useState<number>(want?.coin_type_id ?? collected?.coin_type_id ?? series[0]?.id ?? 0);
  const type = series.find((t) => t.id === typeId);
  const [finish, setFinish] = useState<Finish>(want?.finish ?? "MS");
  const [year, setYear] = useState(want ? String(want.year) : "");
  const [mint, setMint] = useState(want?.mint_mark ?? "P");
  const [variety, setVariety] = useState(want?.variety ?? "");
  const [prefix, setPrefix] = useState(want?.grade_prefix ?? "MS");
  const [grade, setGrade] = useState(want?.grade ? String(want.grade) : "");
  const [max, setMax] = useState(want?.max_price ?? "");
  const [notes, setNotes] = useState(want?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A matching collection of the user's, if they have one (the want then shows "for <collection>").
  const collection = collections.find((c) => c.coin_type_id === typeId && c.finish === finish);

  async function save() {
    const price = parseMoney(max);
    if ("error" in price) return setError(`Max price ${price.error}.`);
    if (!year) return setError("Enter the year.");
    const body: WantIn = {
      collection_id: collection?.id ?? null,
      coin_type_id: typeId,
      finish,
      year: Number(year),
      mint_mark: mint,
      variety: variety || null,
      grade_prefix: grade ? prefix : null,
      grade: grade ? Number(grade) : null,
      max_price: price.value,
      notes: notes || null,
    };
    setBusy(true);
    setError(null);
    try {
      if (want) await api.updateWant(want.id, body);
      else await api.addWant(body);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal want-modal" role="dialog" aria-label={want ? "Edit want" : "Add to want list"} onClick={(e) => e.stopPropagation()}>
        <h2>{want ? "Edit Want" : "Add To Want List"}</h2>
        <label className="field">
          <span>Series</span>
          <select value={typeId} onChange={(e) => setTypeId(Number(e.target.value))}>
            {series.map((t) => (
              <option key={t.id} value={t.id}>
                {t.plural}
              </option>
            ))}
          </select>
        </label>
        <div className="row">
          {type && type.finishes.length > 1 && (
            <label className="field">
              <span>Finish</span>
              <select value={finish} onChange={(e) => setFinish(e.target.value as Finish)}>
                {type.finishes.map((f) => (
                  <option key={f.code} value={f.code}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="field">
            <span>Year</span>
            <input type="number" min={1700} max={new Date().getFullYear() + 1} value={year} onChange={(e) => setYear(e.target.value)} />
          </label>
          <label className="field">
            <span>Mint</span>
            <select value={mint} onChange={(e) => setMint(e.target.value)}>
              {(type?.mint_marks.length ? type.mint_marks : ["P"]).map((m) => (
                <option key={m} value={m}>
                  {m === "P" ? "P (no mint mark)" : m}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          <span>Variety (optional)</span>
          <input value={variety} onChange={(e) => setVariety(e.target.value)} placeholder="e.g. 8TF, 1880/79, VAM-3" />
        </label>
        <div className="row">
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
          <label className="field">
            <span>Max price</span>
            <input type="text" inputMode="decimal" value={max} onChange={(e) => setMax(e.target.value)} placeholder="0.00" />
          </label>
        </div>
        <label className="field">
          <span>Notes</span>
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. only with original toning" />
        </label>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={save}>
            {busy ? "Saving…" : want ? "Save" : "Add"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

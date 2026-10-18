import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { api, type StorageSpotSummary } from "../api";
import { money } from "../format";

/** Where coins and bullion are kept: albums, boxes, or the owner's own codes. */
export default function StoragePage() {
  const [spots, setSpots] = useState<StorageSpotSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .storageSpots()
      .then((s) => live && setSpots(s))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, []);

  if (error) return <div className="page error">{error}</div>;
  if (!spots) return <div className="page muted">Loading…</div>;

  return (
    <div className="page storage-page">
      <div className="page-head">
        <div>
          <h1>Storage</h1>
          <p className="muted small">
            Where your coins and bullion are kept: an album, a box, or a code of your own. Add items here or on their
            edit pages, and print a list for any storage spot.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          + New storage spot
        </button>
      </div>
      {spots.length === 0 ? (
        <div className="card empty-state">
          <p>No storage spots yet. Create one, e.g. "Dansco Peace Album" or "Box #12".</p>
        </div>
      ) : (
        <div className="submission-grid">
          {spots.map((s) => {
            const n = s.coin_count + s.bullion_count;
            return (
              <Link key={s.id} to={`/storage/${s.id}`} className="card storage-card">
                <strong>{s.name}</strong>
                {s.notes && <span className="muted small storage-notes">{s.notes}</span>}
                <span className="small">
                  {n} item{n === 1 ? "" : "s"}
                  {s.bullion_count ? ` (${s.coin_count} coin${s.coin_count === 1 ? "" : "s"}, ${s.bullion_count} bullion)` : ""}
                </span>
                <span className="storage-value">{money(s.value)}</span>
              </Link>
            );
          })}
        </div>
      )}
      {creating && <SpotDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

/** New storage spot, or rename / edit the notes of one. */
export function SpotDialog({
  spot,
  onClose,
  onSaved,
}: {
  spot?: { id: number; name: string; notes: string | null };
  onClose: () => void;
  onSaved?: () => void;
}) {
  const navigate = useNavigate();
  const [name, setName] = useState(spot?.name ?? "");
  const [notes, setNotes] = useState(spot?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Give it a name.");
    setBusy(true);
    setError(null);
    try {
      if (spot) {
        await api.updateStorageSpot(spot.id, { name, notes: notes || null });
        onSaved?.();
        onClose();
      } else {
        const s = await api.createStorageSpot({ name, notes: notes || null });
        navigate(`/storage/${s.id}`);
      }
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="modal" role="dialog" aria-modal="true" aria-label={spot ? "Edit storage spot" : "New storage spot"} onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h2>{spot ? "Edit Storage Spot" : "New Storage Spot"}</h2>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Dansco Peace Album, Box #12" maxLength={100} autoFocus />
        </label>
        <label className="field">
          <span>Notes (optional)</span>
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder='e.g. "In the safe"' maxLength={2000} />
        </label>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : spot ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

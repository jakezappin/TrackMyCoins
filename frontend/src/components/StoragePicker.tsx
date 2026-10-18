import { useEffect, useState } from "react";
import { api, type StorageSpotSummary } from "../api";

/** "Stored in" (a Storage spot, optional) and the position in it, for the coin and bullion forms. "+ New…" creates
 * a storage spot on the spot. */
export default function StoragePicker({
  storageId,
  position,
  onChange,
}: {
  storageId: number | null;
  position: string | null;
  onChange: (storageId: number | null, position: string | null) => void;
}) {
  const [spots, setSpots] = useState<StorageSpotSummary[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .storageSpots()
      .then(setSpots)
      .catch(() => setSpots([]));
  }, []);

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const s = await api.createStorageSpot({ name: name.trim() });
      setSpots((cur) => [...(cur ?? []), s]);
      onChange(s.id, position);
      setAdding(false);
      setName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-3 storage-picker">
      <label className="field">
        <span>Stored in (optional)</span>
        <select
          value={adding ? "new" : storageId ?? ""}
          onChange={(e) => {
            if (e.target.value === "new") return setAdding(true);
            setAdding(false);
            onChange(e.target.value ? Number(e.target.value) : null, e.target.value ? position : null);
          }}
        >
          <option value="">Not specified</option>
          {(spots ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
          <option value="new">+ New storage spot…</option>
        </select>
      </label>
      {adding ? (
        <div className="field">
          <span>New storage spot</span>
          <div className="row tight">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Dansco Peace Album, Box #12"
              maxLength={100}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  create();
                }
              }}
              autoFocus
            />
            <button type="button" className="btn" onClick={create} disabled={busy || !name.trim()}>
              {busy ? "…" : "Add"}
            </button>
          </div>
          {error && <span className="error small">{error}</span>}
        </div>
      ) : (
        storageId != null && (
          <label className="field">
            <span>Position (optional)</span>
            <input
              value={position ?? ""}
              onChange={(e) => onChange(storageId, e.target.value || null)}
              placeholder="e.g. Page 3, hole 14 or Row 2"
              maxLength={60}
            />
          </label>
        )
      )}
    </div>
  );
}

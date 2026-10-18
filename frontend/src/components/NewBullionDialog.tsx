import { useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { api, type Metal } from "../api";
import { useApp } from "../App";
import { METAL_LABEL } from "../bullionFormat";

/** Create a bullion collection: one metal per collection. */
export default function NewBullionDialog({ onClose }: { onClose: () => void }) {
  const { bullionCollections, refresh } = useApp();
  const navigate = useNavigate();
  const [metal, setMetal] = useState<Metal>("silver");
  const count = (m: Metal) => bullionCollections.filter((c) => c.metal === m).length;
  const defaultName = (m: Metal) => `${METAL_LABEL[m]} Bullion${count(m) ? ` ${count(m) + 1}` : ""}`;
  const [name, setName] = useState(defaultName("silver"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const col = await api.createBullionCollection(name.trim(), metal);
      await refresh();
      onClose();
      navigate(`/bullion/${col.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div className="modal" role="dialog" aria-label="New bullion collection" onClick={(e) => e.stopPropagation()}>
        <h2>New Bullion Collection</h2>
        <div className="segmented">
          {(Object.keys(METAL_LABEL) as Metal[]).map((m) => (
            <button
              type="button"
              key={m}
              className={`seg metal-${m} ${metal === m ? "active" : ""}`}
              onClick={() => {
                setMetal(m);
                setName(defaultName(m));
              }}
            >
              {METAL_LABEL[m]}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
        </label>
        <p className="muted small">Bars, rounds, coins, rolls and tubes, valued at today's spot price.</p>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" disabled={busy || !name.trim()} onClick={create}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, type CoinDetail } from "../api";
import { FINISH_LABEL } from "../format";

/** "Move…" button: move a coin to another collection of the same series (shown only when there is one). */
export default function MoveCoin({ coin, onMoved }: { coin: CoinDetail; onMoved: (c: CoinDetail) => void }) {
  const [targets, setTargets] = useState<{ id: number; name: string; finish: string }[]>([]);
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.moveTargets(coin.inventory_number).then((t) => {
      setTargets(t);
      setChoice(t[0]?.id ?? null);
    }).catch(() => setTargets([]));
  }, [coin.inventory_number, coin.collection_id]);

  if (targets.length === 0) return null;

  async function move() {
    if (!choice || busy) return;
    setBusy(true);
    setError(null);
    try {
      onMoved(await api.moveCoin(coin.inventory_number, choice));
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="btn" onClick={() => setOpen(true)}>
        Move…
      </button>
      {open &&
        createPortal(
          <div className="modal-backdrop" onClick={() => setOpen(false)}>
            <div className="modal" role="dialog" aria-label="Move coin" onClick={(e) => e.stopPropagation()}>
              <h2>Move {coin.inventory_number}</h2>
              <p className="muted small">
                From <strong>{coin.collection_name}</strong> to another of your collections. Its inventory number,
                photos and price history come along.
              </p>
              <label className="field">
                <span>Move to</span>
                <select value={choice ?? ""} onChange={(e) => setChoice(Number(e.target.value))}>
                  {targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                      {t.finish !== "MS" ? ` (${FINISH_LABEL[t.finish as keyof typeof FINISH_LABEL]})` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {error && <p className="error small">{error}</p>}
              <div className="row-end">
                <button type="button" className="btn" onClick={() => setOpen(false)}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary" onClick={move} disabled={busy || !choice}>
                  {busy ? "Moving…" : "Move"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

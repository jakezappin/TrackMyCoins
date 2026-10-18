import { useState } from "react";
import { createPortal } from "react-dom";
import { api, type Collection } from "../api";

/** "Share" button + dialog: turn a read-only public link on or off for one collection. */
export default function ShareCollection({
  collection,
  onChange,
  asMenuItem,
}: {
  collection: Collection;
  onChange: (c: Collection) => void;
  /** Render as a plain item inside a drop-down menu instead of a button. */
  asMenuItem?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pendingShow, setPendingShow] = useState(false); // before a link exists
  const shared = Boolean(collection.share_token);
  const link = shared ? `${window.location.origin}/shared/${collection.share_token}` : "";

  async function run(fn: () => Promise<Collection>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Couldn't copy. Select the link and copy it yourself.");
    }
  }

  return (
    <>
      <button type="button" className={asMenuItem ? undefined : "btn"} onClick={() => setOpen(true)}>
        {asMenuItem ? (shared ? "Sharing… (on)" : "Share…") : shared ? "Shared" : "Share"}
      </button>
      {open && createPortal(
        <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={() => !busy && setOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h2>Share “{collection.name}”</h2>
            <p className="muted small">
              Anyone with the link can view this collection without logging in: each coin's date, grade, certification,
              variety, holder, toning and photos. They can't see what you paid, who you bought from, your notes or coins
              you've sold, and they can't change anything.
            </p>
            {shared ? (
              <>
                <div className="share-link">
                  <input readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Share link" />
                  <button className="btn" onClick={copy}>
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <a className="small" href={link} target="_blank" rel="noreferrer">
                  Open the shared page ↗
                </a>
              </>
            ) : null}
            <label className="checks">
              <span>
                <input
                  type="checkbox"
                  checked={shared ? collection.share_show_values : pendingShow}
                  disabled={busy}
                  onChange={(e) => {
                    const v = e.target.checked;
                    if (shared) run(() => api.shareCollection(collection.id, v));
                    else setPendingShow(v);
                  }}
                />{" "}
                Show estimated values
              </span>
            </label>
            {error && <p className="error small">{error}</p>}
            <div className="row-end">
              {shared ? (
                <button className="btn danger-outline" disabled={busy} onClick={() => run(() => api.stopSharing(collection.id))}>
                  Stop sharing
                </button>
              ) : null}
              <button className="btn" onClick={() => setOpen(false)}>
                Close
              </button>
              {!shared && (
                <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.shareCollection(collection.id, pendingShow))}>
                  Create link
                </button>
              )}
            </div>
            {shared && <p className="muted small">Stopping sharing turns this link off for good. Sharing again makes a new link.</p>}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

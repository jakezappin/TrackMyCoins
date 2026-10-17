import { useState } from "react";
import { api, type NgcImages } from "../api";

/**
 * Paste one photo link copied from NGC's cert page; we fetch both sides at full size.
 * (NGC's pages block automated lookups, but its photos are public files.)
 */
export default function NgcPhotoLink({
  expectedCert,
  onFound,
  busyLabel = "Getting photos…",
  actionLabel = "Get NGC photos",
}: {
  expectedCert?: string | null;
  onFound: (r: NgcImages) => Promise<void> | void;
  busyLabel?: string;
  actionLabel?: string;
}) {
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<NgcImages | null>(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.ngcImages(link.trim());
      await onFound(r);
      setFound(r);
      setLink("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const certKey = (c?: string | null) => (c ?? "").replace(/\D/g, "");
  const mismatch = found && expectedCert && certKey(found.cert_number) !== certKey(expectedCert);
  return (
    <div className="ngc-photos">
      <span className="small muted">
        <strong>NGC photos:</strong> on NGC's page, right-click (or long-press) a coin photo, choose{" "}
        <strong>Copy Image Address</strong>, and paste it here. Both sides are saved at full size.
      </span>
      <div className="share-link">
        <input
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="https://ccg-imaging-ngc-coins-production.s3.amazonaws.com/…"
          aria-label="NGC photo link"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (link.trim()) go();
            }
          }}
        />
        <button type="button" className="btn" disabled={busy || !link.trim()} onClick={go}>
          {busy ? busyLabel : actionLabel}
        </button>
      </div>
      {error && <p className="error small">{error}</p>}
      {found && (
        <div className="thumb-row">
          {found.previews.map((u) => (
            <img key={u} className="ngc-thumb" src={u} alt="" />
          ))}
        </div>
      )}
      {mismatch && (
        <p className="warn small">
          These photos are for NGC cert {found.cert_number}, not {expectedCert}. Check you copied the right coin.
        </p>
      )}
    </div>
  );
}

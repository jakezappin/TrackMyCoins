import { useEffect, useRef, useState } from "react";
import { api, type Attachment, type AttachmentOwner } from "../api";
import { shortDate } from "../format";

const sizeLabel = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`);

// What a grading submission's documents are (picked before uploading, shown on each file).
const DOC_KINDS: Record<string, string> = {
  invoice: "Invoice",
  shipping: "Shipping receipt",
  insurance: "Insurance",
  registered: "Registered mail slip",
  other: "Other",
};

/** Receipts, invoices and other documents kept with a coin, bullion item or grading submission (private: never
 * shown on shared links). */
export default function AttachmentsCard({ inventoryNumber, kind = "coin" }: { inventoryNumber: string; kind?: AttachmentOwner }) {
  const [docKind, setDocKind] = useState("invoice");
  const [items, setItems] = useState<Attachment[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const camera = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .attachments(inventoryNumber, kind)
      .then(setItems)
      .catch((e) => setError((e as Error).message));
  }, [inventoryNumber, kind]);

  async function act(label: string, fn: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  const onFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (files.length)
      act("upload", async () => setItems(await api.uploadAttachments(inventoryNumber, files, kind, kind === "grading" ? docKind : undefined)));
  };

  const remove = (a: Attachment) => {
    if (!confirm(`Delete ${a.name}?`)) return;
    act(`del-${a.id}`, async () => {
      await api.deleteAttachment(a.url);
      setItems((cur) => (cur ?? []).filter((x) => x.id !== a.id));
    });
  };

  return (
    <section className="card attachments">
      <div className="section-head">
        <h2>Receipts &amp; Documents</h2>
        <span className="photo-buttons">
          {kind === "grading" && (
            <select value={docKind} onChange={(e) => setDocKind(e.target.value)} aria-label="What the file is" className="w-auto">
              {Object.entries(DOC_KINDS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="btn" disabled={busy !== null} onClick={() => camera.current?.click()}>
            <span className="btn-icon" aria-hidden="true">📷</span>
            Photo
          </button>
          <button type="button" className="btn" disabled={busy !== null} onClick={() => picker.current?.click()}>
            {busy === "upload" ? "Uploading…" : "Add file"}
          </button>
        </span>
        <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={onFiles} />
        <input ref={picker} type="file" accept="application/pdf,.pdf,image/*" multiple hidden onChange={onFiles} />
      </div>
      {items === null && !error && <p className="muted small">Loading…</p>}
      {items?.length === 0 && (
        <p className="muted small">
          {kind === "grading"
            ? "Keep the invoice, shipping and insurance receipts and registered mail slips with the submission. PDFs and photos, up to 10 MB each."
            : "Keep the receipt, invoice or certificate with the coin. PDFs and photos, up to 10 MB each."}
        </p>
      )}
      {items && items.length > 0 && (
        <ul className="attach-list">
          {items.map((a) => (
            <li key={a.id}>
              <span className="attach-icon" aria-hidden="true">
                {a.content_type === "application/pdf" ? "📄" : "🧾"}
              </span>
              <a href={a.url} target="_blank" rel="noopener noreferrer" className="attach-name">
                {a.name}
              </a>
              <span className="muted small">
                {a.kind && kind === "grading" ? `${DOC_KINDS[a.kind] ?? a.kind} · ` : ""}
                {sizeLabel(a.size)} · {shortDate(a.created_at)}
              </span>
              <button
                type="button"
                className="link-btn small icon-x"
                onClick={() => remove(a)}
                disabled={busy !== null}
                aria-label={`Delete ${a.name}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="error small">{error}</p>}
      <p className="muted small">Only you can see these; they're never included on shared links.</p>
    </section>
  );
}

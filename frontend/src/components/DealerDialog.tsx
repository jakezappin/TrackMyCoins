import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, type Dealer, type DealerIn } from "../api";
import PhotoButtons from "./PhotoButtons";
import { loadDealers } from "./DealerInput";

const BLANK: DealerIn = {
  business: null,
  contact_name: null,
  phone: null,
  email: null,
  website: null,
  address: null,
  social: null,
  specialties: [],
  notes: null,
};

/** Add or edit a dealer. Scanning a card or banner fills the fields from the photo (and keeps the photo). */
export default function DealerDialog({
  dealer,
  scanFirst,
  onClose,
  onSaved,
}: {
  dealer?: Dealer;
  /** Open straight to the camera / photo picker (from "Scan card or banner"). */
  scanFirst?: boolean;
  onClose: () => void;
  onSaved: (d: Dealer) => void;
}) {
  const [form, setForm] = useState<DealerIn>(() => (dealer ? { ...BLANK, ...dealer } : BLANK));
  const [tags, setTags] = useState((dealer?.specialties ?? []).join(", "));
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(dealer?.photo_url ?? null);
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!photo) return;
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const set = (k: keyof DealerIn, v: string) => setForm((f) => ({ ...f, [k]: v || null }));

  async function scan(file: File) {
    setPhoto(file);
    setReading(true);
    setReadNote(null);
    setError(null);
    try {
      const r = await api.readDealerCard(file);
      if (!r.found) {
        setReadNote("Couldn't find contact details in that photo. Fill them in yourself; the photo is still kept.");
        return;
      }
      // Fill what was read, keeping anything already typed.
      setForm((f) => ({
        ...f,
        business: f.business || r.business,
        contact_name: f.contact_name || r.contact_name,
        phone: f.phone || r.phone,
        email: f.email || r.email,
        website: f.website || r.website,
        address: f.address || r.address,
        social: f.social || r.social,
        notes: [f.notes, r.notes].filter(Boolean).join("\n") || null,
      }));
      if (r.specialties.length) setTags((t) => [t, r.specialties.join(", ")].filter(Boolean).join(", "));
      setReadNote("Read from your photo. Check it, then save.");
    } catch (e) {
      setReadNote(`${(e as Error).message} The photo is still kept.`);
    } finally {
      setReading(false);
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form.business?.trim() && !form.contact_name?.trim()) return setError("Enter the business or the contact's name.");
    setBusy(true);
    setError(null);
    const body = { ...form, specialties: tags.split(",").map((t) => t.trim()).filter(Boolean) };
    try {
      let saved: Dealer = dealer ? await api.updateDealer(dealer.id, body) : await api.createDealer(body);
      if (photo) {
        try {
          saved = { ...saved, ...(await api.uploadDealerPhoto(saved.id, photo)) };
        } catch {
          // The dealer is saved; the photo can be added again from their page.
        }
      }
      loadDealers(true);
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const field = (k: keyof DealerIn, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="field">
      <span>{label}</span>
      <input value={(form[k] as string | null) ?? ""} onChange={(e) => set(k, e.target.value)} maxLength={200} {...props} />
    </label>
  );

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && !reading && onClose()}>
      <form
        className="modal dealer-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={dealer ? "Edit dealer" : "Add dealer"}
        onClick={(e) => e.stopPropagation()}
        onSubmit={save}
      >
        <h2>{dealer ? "Edit Dealer" : "Add Dealer"}</h2>
        <div className="dealer-scan">
          {preview ? <img src={preview} alt="Card or banner" className="dealer-card-photo" /> : null}
          <div className="stack">
            <PhotoButtons
              onFiles={(fs) => scan(fs[0])}
              multiple={false}
              takeLabel={preview ? "Scan again" : "Scan card or banner"}
              chooseLabel="Choose photo"
              disabled={reading || busy}
              primary={!preview}
            />
            <small className="muted">
              {reading ? "Reading the photo…" : readNote ?? "A photo of their business card or show banner fills this in for you."}
            </small>
            {scanFirst && !preview && !reading && <AutoClick />}
          </div>
        </div>
        <div className="grid-2">
          {field("business", "Business", { placeholder: "Rick's Rare Coins", autoFocus: !scanFirst })}
          {field("contact_name", "Contact name")}
          {field("phone", "Phone", { inputMode: "tel", maxLength: 60 })}
          {field("email", "Email", { type: "email", inputMode: "email" })}
          {field("website", "Website", { placeholder: "ricksrare.com", maxLength: 300 })}
          {field("social", "Social (optional)", { placeholder: "@ricksrare" })}
        </div>
        {field("address", "Address (optional)", { maxLength: 300 })}
        <label className="field">
          <span>Specialties</span>
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Morgans, Gold, CAC" maxLength={500} />
          <small className="muted">Separate with commas.</small>
        </label>
        <label className="field">
          <span>Notes</span>
          <textarea
            rows={3}
            value={form.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            placeholder="Baltimore Expo, booth 1123. Sells mostly Morgans; looking for MS Franklins."
            maxLength={5000}
          />
        </label>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose} disabled={busy || reading}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy || reading}>
            {busy ? "Saving…" : dealer ? "Save" : "Save dealer"}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

/** Opens the camera once when the dialog is opened from "Scan card or banner". */
function AutoClick() {
  useEffect(() => {
    const btn = document.querySelector<HTMLButtonElement>(".dealer-dialog .photo-buttons .btn");
    btn?.click();
  }, []);
  return null;
}

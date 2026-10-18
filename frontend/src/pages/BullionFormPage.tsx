import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type BullionItemIn, type BullionMeta } from "../api";
import { useApp, useNavCollection } from "../App";
import { FACE_NOTE, FACE_OZ, METAL_LABEL, PACKAGING_LABEL, purityLabel, pureOz } from "../bullionFormat";
import { money, parseMoney, todayISO } from "../format";

const EMPTY: Omit<BullionItemIn, "collection_id"> = {
  description: "",
  packaging: "single",
  quantity: 1,
  weight: "1",
  weight_unit: "ozt",
  purity: "0.999",
  face_value: null,
  price_paid: null,
  purchase_date: null,
  purchased_from: null,
  sale_price: null,
  sale_date: null,
  sold_to: null,
  notes: null,
};

/** Add or edit a bullion item: what it is, how much metal, and the purchase (and sale) details. */
export default function BullionFormPage() {
  const { inv } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { bullionCollections, refresh } = useApp();
  const [meta, setMeta] = useState<BullionMeta | null>(null);
  const [collectionId, setCollectionId] = useState<number | null>(Number(search.get("collection")) || null);
  const [form, setForm] = useState(EMPTY);
  const [byFace, setByFace] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.bullionMeta().then(setMeta).catch((e) => setError((e as Error).message));
  }, []);
  useEffect(() => {
    if (!inv) return;
    api
      .bullionItem(inv)
      .then((i) => {
        setCollectionId(i.collection_id);
        setByFace(i.face_value != null);
        setForm({
          description: i.description, packaging: i.packaging, quantity: i.quantity, weight: i.weight,
          weight_unit: i.weight_unit, purity: String(Number(i.purity)), face_value: i.face_value, price_paid: i.price_paid,
          purchase_date: i.purchase_date, purchased_from: i.purchased_from, sale_price: i.sale_price, sale_date: i.sale_date,
          sold_to: i.sold_to, notes: i.notes,
        });
      })
      .catch((e) => setError((e as Error).message));
  }, [inv]);
  useEffect(() => {
    if (collectionId === null && bullionCollections.length) setCollectionId(bullionCollections[0].id);
  }, [bullionCollections, collectionId]);

  const col = bullionCollections.find((c) => c.id === collectionId);
  useNavCollection("bullion", collectionId);
  const metal = col?.metal ?? "silver";
  const purities = meta?.purities[metal] ?? [];
  const faceAllowed = metal === "silver";
  // Keep the purity one this metal offers.
  useEffect(() => {
    if (purities.length && !purities.includes(String(Number(form.purity)))) setForm((f) => ({ ...f, purity: purities[1] ?? purities[0] }));
  }, [metal, purities.join()]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const text = (k: "description" | "purchased_from" | "sold_to" | "notes") => ({
    value: form[k] ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => set(k, e.target.value || null),
  });
  const amount = byFace ? { ...form, weight: null } : { ...form, face_value: null };
  const oz = pureOz(amount);
  const spot = meta?.spot[metal];
  const sameCollections = inv && col ? bullionCollections.filter((c) => c.metal === col.metal) : bullionCollections;
  const facePurities = useMemo(() => Object.keys(FACE_OZ), []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!collectionId) return setError("Create a bullion collection first.");
    const money_ = (label: string, v: string | null) => {
      const r = parseMoney(v);
      if ("error" in r) throw new Error(`${label} ${r.error}.`);
      return r.value;
    };
    let body: BullionItemIn;
    try {
      body = {
        ...form,
        collection_id: collectionId,
        weight: byFace ? null : form.weight,
        face_value: byFace ? money_("Face value", form.face_value) : null,
        quantity: byFace ? 1 : Number(form.quantity) || 1,
        price_paid: money_("Price paid", form.price_paid),
        sale_price: money_("Sale price", form.sale_price),
      };
    } catch (err) {
      return setError((err as Error).message);
    }
    setSaving(true);
    setError(null);
    try {
      const item = inv ? await api.updateBullionItem(inv, body) : await api.createBullionItem(body);
      refresh();
      navigate(`/bullion/items/${item.inventory_number}`);
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }

  if (!bullionCollections.length)
    return (
      <div className="page">
        <div className="card empty-state">
          <h2>No Bullion Collections Yet</h2>
          <p className="muted">Create one from the sidebar (Bullion → New bullion collection).</p>
        </div>
      </div>
    );

  return (
    <form className="page" onSubmit={save}>
      <div className="page-head">
        <h1>{inv ? `Edit ${inv}` : "Add Bullion"}</h1>
        <div className="row">
          <Link className="btn" to={inv ? `/bullion/items/${inv}` : col ? `/bullion/${col.id}` : "/dashboard"}>
            Cancel
          </Link>
          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
      {error && <p className="error banner">{error}</p>}

      <section className="card form-section">
        <h2>Bullion</h2>
        <div className="grid-2">
          <label className="field">
            <span>Collection</span>
            <select value={collectionId ?? ""} onChange={(e) => setCollectionId(Number(e.target.value))}>
              {sameCollections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({METAL_LABEL[c.metal]})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Description</span>
            <input {...text("description")} required maxLength={200} placeholder="e.g. Buffalo Round, Silvertown Bar, Silver Eagles" />
          </label>
        </div>

        <div className="grid-4">
          <label className="field">
            <span>Purity</span>
            <select
              value={String(Number(form.purity))}
              onChange={(e) => {
                set("purity", e.target.value);
                if (!facePurities.includes(e.target.value)) setByFace(false);
              }}
            >
              {purities.map((p) => (
                <option key={p} value={String(Number(p))}>
                  {purityLabel(p)}
                </option>
              ))}
            </select>
          </label>
          {faceAllowed && facePurities.includes(String(Number(form.purity))) && (
            <div className="field">
              <span>Enter by</span>
              <div className="segmented">
                <button type="button" className={`seg ${!byFace ? "active" : ""}`} onClick={() => setByFace(false)}>
                  Weight
                </button>
                <button type="button" className={`seg ${byFace ? "active" : ""}`} onClick={() => setByFace(true)}>
                  Face value
                </button>
              </div>
            </div>
          )}
          {byFace ? (
            <label className="field">
              <span>Face value</span>
              <input
                type="text"
                inputMode="decimal"
                value={form.face_value ?? ""}
                onChange={(e) => set("face_value", e.target.value || null)}
                placeholder="10.00"
                required
              />
              <small className="muted">{FACE_NOTE[String(Number(form.purity))]}</small>
            </label>
          ) : (
            <>
              <label className="field">
                <span>Weight (each piece)</span>
                <div className="row tight">
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={form.weight ?? ""}
                    onChange={(e) => set("weight", e.target.value || null)}
                    required
                  />
                  <select value={form.weight_unit} onChange={(e) => set("weight_unit", e.target.value as BullionItemIn["weight_unit"])} className="w-auto">
                    <option value="ozt">ozt</option>
                    <option value="g">grams</option>
                    <option value="kg">kilos</option>
                  </select>
                </div>
              </label>
              <label className="field">
                <span>Packaging</span>
                <select
                  value={form.packaging}
                  onChange={(e) => {
                    const p = e.target.value as BullionItemIn["packaging"];
                    setForm((f) => ({ ...f, packaging: p, quantity: p === "single" ? 1 : Math.max(f.quantity, 1) }));
                  }}
                >
                  {Object.entries(PACKAGING_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{form.packaging === "single" ? "Quantity" : "Pieces in it"}</span>
                <input type="number" min={1} step={1} value={form.quantity} onChange={(e) => set("quantity", Number(e.target.value))} required />
              </label>
            </>
          )}
        </div>
        <p className="muted bullion-preview">
          {oz != null ? (
            <>
              ≈ <strong>{oz.toFixed(4)} ozt</strong> pure {METAL_LABEL[metal].toLowerCase()}
              {spot && <> · {money(oz * Number(spot))} at today's spot ({money(spot)}/ozt)</>}
            </>
          ) : (
            "Enter the weight to see the metal content."
          )}
        </p>
      </section>

      <div className="grid-2">
        <section className="card form-section">
          <h2>Purchase</h2>
          <div className="grid-2">
            <label className="field">
              <span>Price paid (total)</span>
              <input type="text" inputMode="decimal" value={form.price_paid ?? ""} onChange={(e) => set("price_paid", e.target.value || null)} placeholder="0.00" />
            </label>
            <label className="field">
              <span>Date purchased</span>
              <input type="date" min="1900-01-01" max={todayISO()} value={form.purchase_date ?? ""} onChange={(e) => set("purchase_date", e.target.value || null)} />
            </label>
          </div>
          <label className="field">
            <span>Purchased from</span>
            <input {...text("purchased_from")} placeholder="Dealer, show, online…" />
          </label>
        </section>
        <section className="card form-section">
          <h2>Sale</h2>
          <div className="grid-2">
            <label className="field">
              <span>Sale price</span>
              <input type="text" inputMode="decimal" value={form.sale_price ?? ""} onChange={(e) => set("sale_price", e.target.value || null)} placeholder="0.00" />
            </label>
            <label className="field">
              <span>Sale date</span>
              <input type="date" min="1900-01-01" max={todayISO()} value={form.sale_date ?? ""} onChange={(e) => set("sale_date", e.target.value || null)} />
            </label>
          </div>
          <label className="field">
            <span>Sold to</span>
            <input {...text("sold_to")} />
          </label>
          <p className="muted small">Selling only part of a roll or tube? Use Sell on the item's page instead.</p>
        </section>
      </div>

      <section className="card form-section">
        <h2>Notes</h2>
        <textarea rows={3} {...text("notes")} />
        {!inv && <p className="muted small">Add photos on the item's page after saving.</p>}
      </section>
    </form>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  ApiError,
  type CatalogCandidate,
  type CoinFields,
  type DuplicateCert,
  type GradingService,
  type LookupResult,
} from "../api";
import DuplicateCertModal from "../components/DuplicateCertModal";
import { useApp } from "../App";
import { coinPath, collectionsBySeries, FINISH_LABEL, money } from "../format";

const EMPTY: CoinFields = {
  year: null,
  mint_mark: "P",
  vam: null,
  variety: null,
  pcgs_number: null,
  grading_service: "PCGS",
  cert_number: null,
  grade_prefix: "MS",
  grade: null,
  grade_plus: false,
  grade_star: false,
  strike_designation: null,
  cac: false,
  cac_sticker: null,
  slab_soapbox: false,
  slab_ngc_fatty: false,
  slab_rattler: false,
  slab_ogh: false,
  gsa_hard_pack: false,
  gsa_soft_pack: false,
  ike_blue_pack: false,
  ike_brown_pack: false,
  toning_obverse: false,
  toning_reverse: false,
  toning_dual: false,
  toning_rainbow: false,
  price_paid: null,
  purchase_date: null,
  purchased_from: null,
  sale_price: null,
  sale_date: null,
  sold_to: null,
  notes: null,
};

const SERVICES: GradingService[] = ["PCGS", "NGC", "ANACS", "CACG", "RAW"];
const CIRC_PREFIXES = ["MS", "AU", "XF", "VF", "F", "VG", "G", "AG"];
// Used until the catalog's designations for the series load (or if it can't be reached).
const FALLBACK_DESIGNATIONS: Record<string, string[]> = {
  MS: ["PL", "DMPL", "RD", "RB", "BN", "FB", "FS", "FH"],
  PR: ["CAM", "DCAM", "RD", "RB", "BN"],
};
const VAM_SERIES = ["morgan-dollars", "peace-dollars"];
// Series sold by the GSA in its hard and soft pack holders.
const GSA_SERIES = ["morgan-dollars", "peace-dollars"];
type PackKey = "gsa_hard_pack" | "gsa_soft_pack" | "ike_blue_pack" | "ike_brown_pack";
const VARIETY_HINTS: Record<string, string> = {
  "classic-commemoratives": "e.g. Alabama, Boone",
  "washington-quarters": "Design from 1999 on, e.g. Delaware, Yellowstone",
};

function verifyUrl(service: GradingService, cert: string, grade: number | null): string | null {
  if (!cert) return null;
  switch (service) {
    case "PCGS":
      return `https://www.pcgs.com/cert/${encodeURIComponent(cert)}`;
    case "NGC":
      return `https://www.ngccoin.com/certlookup/${encodeURIComponent(cert)}/${grade ? `?grade=${grade}` : ""}`;
    case "ANACS":
      return "https://anacs.com/verify/";
    case "CACG":
      return `https://www.cacgrading.com/lookup/${encodeURIComponent(cert)}`;
    default:
      return null;
  }
}

export default function CoinFormPage() {
  const params = useParams();
  const editInv = params.inv ?? null;
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { collections, coinTypes, refresh } = useApp();

  const [form, setForm] = useState<CoinFields>(EMPTY);
  const [collectionId, setCollectionId] = useState<number | null>(Number(search.get("collection")) || null);
  const [inventoryNumber, setInventoryNumber] = useState<string | null>(null);
  const [loading, setLoading] = useState(editInv !== null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookup, setLookup] = useState<LookupResult | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [importUrls, setImportUrls] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [findBusy, setFindBusy] = useState(false);
  const [findMsg, setFindMsg] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CatalogCandidate[]>([]);
  const [dup, setDup] = useState<{ service: string; cert: string; duplicate: DuplicateCert } | null>(null);

  useEffect(() => {
    if (editInv === null) return;
    api
      .coin(editInv)
      .then((c) => {
        const fields = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, c[k as keyof CoinFields]])) as unknown as CoinFields;
        setForm(fields);
        setCollectionId(c.collection_id);
        setInventoryNumber(c.inventory_number);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [editInv]);

  // Default to the first collection when adding without one selected.
  useEffect(() => {
    if (collectionId === null && collections.length) setCollectionId(collections[0].id);
  }, [collections, collectionId]);

  const collection = collections.find((c) => c.id === collectionId);
  const coinType = coinTypes.find((t) => t.id === collection?.coin_type_id) ?? coinTypes[0];
  const finish = collection?.finish ?? "MS";
  const isProof = finish !== "MS";
  const isRaw = form.grading_service === "RAW";
  // Packaging checkboxes that apply to this series/finish: [field, label, the field it excludes].
  const packaging: [PackKey, string, PackKey | null][] = [];
  if (coinType && GSA_SERIES.includes(coinType.slug)) {
    packaging.push(["gsa_hard_pack", "GSA Hard Pack", "gsa_soft_pack"], ["gsa_soft_pack", "GSA Soft Pack", "gsa_hard_pack"]);
  }
  if (coinType?.slug === "ike-dollars") {
    packaging.push(isProof ? ["ike_brown_pack", "Brown Pack (40% silver proof)", null] : ["ike_blue_pack", "Blue Pack (40% silver)", null]);
  }
  // When editing, a coin can only move between collections of its own series. Grouped by series.
  const collectionGroups = useMemo(() => {
    const pool = editInv && collection ? collections.filter((c) => c.coin_type_id === collection.coin_type_id) : collections;
    return collectionsBySeries(coinTypes, pool);
  }, [collections, coinTypes, collection, editInv]);

  // Proof collections take PR grades; business-strike collections take MS and circulated grades.
  useEffect(() => {
    if (!collection) return;
    setForm((f) => {
      if (isProof && f.grade_prefix !== "PR") return { ...f, grade_prefix: "PR" };
      if (!isProof && f.grade_prefix === "PR") return { ...f, grade_prefix: "MS" };
      return f;
    });
  }, [collection, isProof]);

  // Designations that exist for this series and finish, from the Greysheet catalog.
  const [designations, setDesignations] = useState<string[] | null>(null);
  useEffect(() => {
    if (!coinType) return;
    let cancelled = false;
    setDesignations(null);
    api
      .designations(coinType.id, finish)
      .then((d) => !cancelled && setDesignations(d))
      .catch(() => !cancelled && setDesignations(FALLBACK_DESIGNATIONS[isProof ? "PR" : "MS"]));
    return () => {
      cancelled = true;
    };
  }, [coinType, finish, isProof]);
  const designationOptions = useMemo(() => {
    const opts = designations ?? FALLBACK_DESIGNATIONS[isProof ? "PR" : "MS"];
    return form.strike_designation && !opts.includes(form.strike_designation) ? [...opts, form.strike_designation] : opts;
  }, [designations, isProof, form.strike_designation]);

  function setRaw(raw: boolean) {
    setForm((f) =>
      raw
        ? {
            ...f,
            grading_service: "RAW",
            cert_number: null,
            cac: false,
            cac_sticker: null,
            grade_plus: false,
            grade_star: false,
            slab_soapbox: false,
            slab_ngc_fatty: false,
            slab_rattler: false,
            slab_ogh: false,
          }
        : { ...f, grading_service: "PCGS" },
    );
    setLookup(null);
    setLookupError(null);
  }

  function set<K extends keyof CoinFields>(key: K, value: CoinFields[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }
  const text = (key: keyof CoinFields) => ({
    value: (form[key] as string | number | null) ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      set(key, (e.target.value === "" ? null : e.target.value) as never),
  });
  const check = (key: keyof CoinFields) => ({
    checked: Boolean(form[key]),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(key, e.target.checked as never),
  });

  /** Warn (and return true) if this cert is already on hand in one of the user's collections. */
  async function checkDuplicate(): Promise<boolean> {
    const cert = form.cert_number?.trim();
    if (!cert || form.grading_service === "RAW") return false;
    try {
      const { duplicate } = await api.certCheck(form.grading_service, cert, editInv);
      if (duplicate) {
        setDup({ service: form.grading_service, cert, duplicate });
        return true;
      }
    } catch {
      // The save will still be checked by the server.
    }
    return false;
  }

  async function doLookup() {
    if (!form.cert_number) return;
    if (await checkDuplicate()) return;
    setLookupBusy(true);
    setLookupError(null);
    setLookup(null);
    try {
      const r = await api.lookup(form.grading_service, form.cert_number);
      setLookup(r);
      setForm((f) => ({
        ...f,
        cert_number: r.cert_number,
        year: r.year ?? f.year,
        mint_mark: r.mint_mark ?? f.mint_mark,
        grade_prefix: r.grade_prefix ?? f.grade_prefix,
        grade: r.grade ?? f.grade,
        grade_plus: r.grade ? r.grade_plus : f.grade_plus,
        grade_star: r.grade ? r.grade_star : f.grade_star,
        strike_designation: r.strike_designation ?? f.strike_designation,
        vam: r.vam ?? f.vam,
        pcgs_number: r.pcgs_number ?? f.pcgs_number,
        cac: r.cac ?? f.cac,
        cac_sticker: r.cac === null ? f.cac_sticker : r.cac_sticker,
      }));
      setImportUrls(r.image_urls);
    } catch (e) {
      setLookupError((e as Error).message);
    } finally {
      setLookupBusy(false);
    }
  }

  async function findPcgs() {
    if (!coinType || !form.year) {
      setFindMsg("Enter the year and mint first.");
      return;
    }
    setFindBusy(true);
    setFindMsg(null);
    setCandidates([]);
    try {
      const m = await api.catalogMatch({
        coin_type_id: coinType.id,
        year: Number(form.year),
        mint_mark: form.mint_mark,
        designation: form.strike_designation,
        finish,
        variety: form.variety,
        gsa: form.gsa_hard_pack ? "hard" : form.gsa_soft_pack ? "soft" : null,
      });
      if (m.best?.pcgs_number) {
        set("pcgs_number", m.best.pcgs_number);
        if (m.best.variety) set("variety", m.best.variety);
        setFindMsg(`Matched ${m.best.name}${m.best.variety ? ` (${m.best.variety})` : ""}`);
      } else {
        setFindMsg(m.message);
        setCandidates(m.candidates);
      }
    } catch (e) {
      setFindMsg((e as Error).message);
    } finally {
      setFindBusy(false);
    }
  }

  function pickCandidate(c: CatalogCandidate) {
    set("pcgs_number", c.pcgs_number);
    set("variety", c.variety);
    setCandidates([]);
    setFindMsg(`Picked ${c.name}${c.variety ? ` (${c.variety})` : ""}`);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!collectionId) {
      setError("Choose a collection (create one from the sidebar first).");
      return;
    }
    setSaving(true);
    setError(null);
    const body = { ...form, collection_id: collectionId, year: form.year ? Number(form.year) : null, grade: form.grade ? Number(form.grade) : null };
    try {
      let coin = editInv
        ? await api.updateCoin(editInv, body)
        : await api.createCoin({ ...body, lookup_raw: lookup?.raw ?? undefined });
      const room = 10 - coin.photos.length;
      if (importUrls.length && room > 0) {
        try {
          coin = await api.importPhotos(coin.inventory_number, importUrls.slice(0, room));
        } catch (err) {
          alert(`Coin saved, but grading-service photos couldn't be imported: ${(err as Error).message}`);
        }
      }
      if (files.length) {
        try {
          coin = await api.uploadPhotos(coin.inventory_number, files.slice(0, 10 - coin.photos.length));
        } catch (err) {
          alert(`Coin saved, but photo upload failed: ${(err as Error).message}`);
        }
      }
      await refresh();
      navigate(coinPath(coin.inventory_number));
    } catch (err) {
      if (err instanceof ApiError && err.duplicate) {
        setDup({ service: form.grading_service, cert: form.cert_number ?? "", duplicate: err.duplicate });
      } else {
        setError((err as Error).message);
      }
      setSaving(false);
    }
  }

  if (loading) return <div className="page muted">Loading…</div>;
  if (!collections.length)
    return (
      <div className="page">
        <h1>Add coin</h1>
        <div className="card empty-state">
          <p>Create a collection first, then add coins to it.</p>
          <Link className="btn btn-primary" to="/dashboard">
            Go to dashboard
          </Link>
        </div>
      </div>
    );

  const vurl = lookup?.verify_url && form.grading_service !== "NGC" ? lookup.verify_url : verifyUrl(form.grading_service, form.cert_number ?? "", form.grade);
  const isSold = Boolean(form.sale_price || form.sale_date);

  return (
    <form className="page coin-form" onSubmit={submit}>
      <div className="page-head">
        <h1>{editInv ? `Edit ${inventoryNumber}` : "Add coin"}</h1>
        <div className="row">
          <button type="button" className="btn" onClick={() => navigate(-1)}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save coin"}
          </button>
        </div>
      </div>
      {error && <p className="error banner">{error}</p>}
      {dup && <DuplicateCertModal {...dup} onClose={() => setDup(null)} />}

      {/* ---- Lookup ---- */}
      <section className="card form-section lookup">
        <div className="section-head">
          <h2>Grading service</h2>
          <label className="raw-toggle">
            <input type="checkbox" checked={isRaw} onChange={(e) => setRaw(e.target.checked)} /> Raw (ungraded)
          </label>
        </div>
        {isRaw ? (
          <p className="muted small">
            Not in a grading-service slab. Grade it yourself below if you like: a letter grade (AU), a letter grade
            with a number (AU55), or leave it blank.
          </p>
        ) : (
        <div className="lookup-bar">
          <label className="field">
            <span>Service</span>
            <select {...text("grading_service")}>
              {SERVICES.filter((s) => s !== "RAW").map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          {
            <>
              <label className="field grow">
                <span>Cert number</span>
                <input
                  {...text("cert_number")}
                  placeholder="e.g. 12345678"
                  onBlur={checkDuplicate}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      doLookup();
                    }
                  }}
                />
              </label>
              <button type="button" className="btn btn-primary" onClick={doLookup} disabled={!form.cert_number || lookupBusy}>
                {lookupBusy ? "Looking up…" : "Look up"}
              </button>
              {vurl && (
                <a className="btn" href={vurl} target="_blank" rel="noreferrer">
                  Verify ↗
                </a>
              )}
            </>
          }
        </div>
        )}
        {lookupError && <p className="error">{lookupError}</p>}
        {lookup && (
          <div className="lookup-result">
            {lookup.description && <p className="strong">{lookup.description}</p>}
            {lookup.price_guide_value && (
              <p className="muted small">PCGS Price Guide: {money(lookup.price_guide_value)}</p>
            )}
            {lookup.warnings.map((w) => (
              <p key={w} className="warn small">
                {w}
              </p>
            ))}
            {lookup.image_urls.length > 0 && (
              <div className="import-photos">
                <span className="small muted">Photos from {lookup.grading_service} (checked ones are saved with the coin):</span>
                <div className="thumb-row">
                  {lookup.image_urls.map((u) => (
                    <label key={u} className="import-thumb">
                      <img src={u} alt="" />
                      <input
                        type="checkbox"
                        checked={importUrls.includes(u)}
                        onChange={(e) =>
                          setImportUrls((cur) => (e.target.checked ? [...cur, u] : cur.filter((x) => x !== u)))
                        }
                      />
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ---- Coin ---- */}
      <section className="card form-section">
        <h2>Coin</h2>
        <div className="grid-4">
          <label className="field">
            <span>Collection</span>
            <select value={collectionId ?? ""} onChange={(e) => setCollectionId(Number(e.target.value))}>
              {collectionGroups.map(({ type, collections: cols }) => (
                <optgroup key={type.id} label={type.plural}>
                  {cols.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.finish !== "MS" ? ` (${FINISH_LABEL[c.finish]})` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Year</span>
            <input type="number" min={1700} max={2200} required {...text("year")} />
          </label>
          <label className="field">
            <span>Mint</span>
            <select {...text("mint_mark")} required>
              {(coinType?.mint_marks ?? ["P"]).map((m) => (
                <option key={m} value={m}>
                  {m === "P" ? "P (no mint mark)" : m}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Variety / issue (optional)</span>
            <input
              {...text("variety")}
              placeholder={VARIETY_HINTS[coinType?.slug ?? ""] ?? "e.g. 8TF, Type 2"}
              maxLength={150}
            />
          </label>
        </div>
        {coinType && VAM_SERIES.includes(coinType.slug) && (
          <div className="grid-4">
            <label className="field">
              <span>VAM (optional)</span>
              <input {...text("vam")} placeholder="e.g. VAM-1A" />
            </label>
          </div>
        )}
        <div className="grid-4">
          <label className="field">
            <span>{isRaw ? "Grade (optional)" : "Grade"}</span>
            <div className="row tight">
              <select {...text("grade_prefix")} className="w-auto" disabled={isProof}>
                {isProof ? (
                  <option value="PR">PR</option>
                ) : (
                  <>
                    <option value="">—</option>
                    {CIRC_PREFIXES.map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </>
                )}
              </select>
              <input type="number" min={1} max={70} {...text("grade")} placeholder="65" />
            </div>
          </label>
          <label className="field">
            <span>Strike designation</span>
            <select {...text("strike_designation")}>
              <option value="">None</option>
              {designationOptions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            <span>Modifiers</span>
            <div className="checks">
              <label>
                <input type="checkbox" disabled={isRaw} {...check("grade_plus")} /> Plus (+)
              </label>
              <label>
                <input type="checkbox" disabled={isRaw} {...check("grade_star")} /> Star (★)
              </label>
            </div>
          </div>
          <label className="field">
            <span>PCGS coin # (for pricing)</span>
            <div className="row tight">
              <input {...text("pcgs_number")} placeholder="e.g. 7226" />
              <button type="button" className="btn" onClick={findPcgs} disabled={findBusy} title="Find from date, mint and designation">
                {findBusy ? "…" : "Find"}
              </button>
            </div>
          </label>
        </div>
        {findMsg && <p className="small muted find-msg">{findMsg}</p>}
        {candidates.length > 0 && (
          <div className="candidates">
            {candidates.map((c) => (
              <button type="button" key={c.gsid} className="candidate" onClick={() => pickCandidate(c)} disabled={!c.pcgs_number}>
                <span className="mono">#{c.pcgs_number ?? "—"}</span>
                <span>{c.name}</span>
                {c.variety && <span className="muted">{c.variety}</span>}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ---- CAC / slab / packaging / toning ---- */}
      <div className="grid-3">
        <section className={`card form-section ${isRaw ? "not-applicable" : ""}`}>
          <h2>CAC</h2>
          <div className="checks col">
            <label>
              <input
                type="checkbox"
                disabled={isRaw}
                checked={form.cac}
                onChange={(e) => setForm((f) => ({ ...f, cac: e.target.checked, cac_sticker: e.target.checked ? f.cac_sticker ?? "green" : null }))}
              />{" "}
              CAC approved
            </label>
            {form.cac && !isRaw && (
              <div className="segmented">
                {(["green", "gold"] as const).map((s) => (
                  <button
                    type="button"
                    key={s}
                    className={`seg ${form.cac_sticker === s ? `active cac-${s}` : ""}`}
                    onClick={() => set("cac_sticker", s)}
                  >
                    {s === "green" ? "Green bean" : "Gold bean"}
                  </button>
                ))}
              </div>
            )}
            {isRaw && <p className="muted small">Not applicable to raw coins</p>}
          </div>
        </section>
        <section className="card form-section">
          <h2>Collector slab</h2>
          <div className={`checks col ${isRaw ? "not-applicable" : ""}`}>
            {(
              [
                ["slab_soapbox", "Soapbox"],
                ["slab_ngc_fatty", "NGC Fatty"],
                ["slab_rattler", "Rattler"],
                ["slab_ogh", "OGH"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                <input type="checkbox" disabled={isRaw} {...check(key)} /> {label}
              </label>
            ))}
            {isRaw && <p className="muted small">Not applicable to raw coins</p>}
          </div>
          {packaging.length > 0 && (
            <>
              <h3 className="subhead">Packaging</h3>
              <div className="checks col">
                {packaging.map(([key, label, other]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={form[key]}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, [key]: e.target.checked, ...(other ? { [other]: false } : {}) }))
                      }
                    />{" "}
                    {label}
                  </label>
                ))}
              </div>
            </>
          )}
        </section>
        <section className="card form-section">
          <h2>Toning</h2>
          <div className="checks col">
            <label>
              <input type="checkbox" {...check("toning_obverse")} /> Obverse
            </label>
            <label>
              <input type="checkbox" {...check("toning_reverse")} /> Reverse
            </label>
            <label>
              <input type="checkbox" {...check("toning_dual")} /> Dual side
            </label>
            <label>
              <input type="checkbox" {...check("toning_rainbow")} /> Rainbow
            </label>
          </div>
        </section>
      </div>

      {/* ---- Purchase / sale ---- */}
      <div className="grid-2">
        <section className="card form-section">
          <h2>Purchase</h2>
          <div className="grid-2">
            <label className="field">
              <span>Amount paid</span>
              <input type="number" step="0.01" min={0} {...text("price_paid")} placeholder="0.00" />
            </label>
            <label className="field">
              <span>Date purchased</span>
              <input type="date" {...text("purchase_date")} />
            </label>
          </div>
          <label className="field">
            <span>Purchased from</span>
            <input {...text("purchased_from")} placeholder="Dealer, show, auction…" />
          </label>
        </section>
        <section className={`card form-section ${isSold ? "sold-section" : ""}`}>
          <h2>Sale {isSold && <span className="tag sold">Sold</span>}</h2>
          <div className="grid-2">
            <label className="field">
              <span>Sale price</span>
              <input type="number" step="0.01" min={0} {...text("sale_price")} placeholder="0.00" />
            </label>
            <label className="field">
              <span>Sale date</span>
              <input type="date" {...text("sale_date")} />
            </label>
          </div>
          <label className="field">
            <span>Sold to</span>
            <input {...text("sold_to")} />
          </label>
          <p className="muted small">Filling in a sale moves the coin to the Sold list.</p>
        </section>
      </div>

      {/* ---- Notes / photos ---- */}
      <section className="card form-section">
        <h2>Notes</h2>
        <textarea rows={4} {...text("notes")} />
      </section>

      {!editInv && (
        <section className="card form-section">
          <h2>Photos</h2>
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 10 - importUrls.length))}
          />
          <p className="muted small">
            Up to 10 photos per coin, including any imported from the grading service. You can add or remove photos
            later on the coin page.
          </p>
        </section>
      )}
    </form>
  );
}

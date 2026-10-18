import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { api, type Collection, type Finish, type Metal } from "../api";
import { useApp } from "../App";
import { METAL_LABEL } from "../bullionFormat";

interface Props {
  /** Pre-select a coin collection type, e.g. "kennedy-half-dollars-proof" (skips the Numismatic / Bullion step). */
  initialType?: string;
  onClose: () => void;
  /** A coin collection was made (bullion collections open their own page). */
  onCreated: (c: Collection) => void;
}

type Kind = "numismatic" | "bullion";
type Region = "us" | "world" | "ancient";

const FINISH_WORD: Record<Finish, string> = { MS: "", PR: " Proof", SPR: " Silver Proof" };
const FINISH_CHOICE: Record<Finish, string> = { MS: "Business strike", PR: "Proof", SPR: "Silver Proof" };
const REGIONS: [Region, string][] = [
  ["us", "U.S. Coins"],
  ["world", "World Coins"],
  ["ancient", "Ancient Coins"],
];

/** One "+ New collection" for everything: Numismatic (region › category › series › finish) or Bullion (metal). */
export default function NewCollectionDialog({ initialType, onClose, onCreated }: Props) {
  const { coinTypes, collections, bullionCollections, refresh } = useApp();
  const navigate = useNavigate();

  const preset = useMemo(() => {
    for (const t of coinTypes) {
      const f = t.finishes.find((x) => x.collection_type_slug === initialType);
      if (f) return { type: t, finish: f.code };
    }
    return null;
  }, [coinTypes, initialType]);

  const [kind, setKind] = useState<Kind | null>(preset ? "numismatic" : null);
  const [region, setRegion] = useState<Region>("us");
  // Categories in the app's own order (Half Cents & Cents, Nickels & Three Cents, ... Type Sets).
  const categories = useMemo(() => [...new Set(coinTypes.map((t) => t.category))], [coinTypes]);
  const [category, setCategory] = useState(preset?.type.category ?? "");
  const [typeId, setTypeId] = useState<number | null>(preset?.type.id ?? null);
  const type = coinTypes.find((t) => t.id === typeId);
  const [finish, setFinish] = useState<Finish>(preset?.finish ?? "MS");
  const [metal, setMetal] = useState<Metal>("silver");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const coinName = (t: (typeof coinTypes)[number], f: Finish) => {
    const slug = t.finishes.find((x) => x.code === f)?.collection_type_slug;
    const n = collections.filter((c) => c.collection_type_slug === slug).length + 1;
    return `${t.name}${FINISH_WORD[f]} Collection ${n}`;
  };
  const bullionName = (m: Metal) => {
    const n = bullionCollections.filter((c) => c.metal === m).length;
    return `${METAL_LABEL[m]} Bullion${n ? ` ${n + 1}` : ""}`;
  };
  // The name follows the choices until the user types their own.
  const suggested = kind === "bullion" ? bullionName(metal) : type ? coinName(type, finish) : "";
  const shownName = nameTouched ? name : suggested;

  function chooseType(id: number | null) {
    setTypeId(id);
    const t = coinTypes.find((x) => x.id === id);
    if (t && !t.finishes.some((f) => f.code === finish)) setFinish(t.finishes[0].code);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!shownName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === "bullion") {
        const col = await api.createBullionCollection(shownName.trim(), metal);
        await refresh();
        onClose();
        navigate(`/bullion/${col.id}`);
      } else if (type) {
        const c = await api.createCollection(shownName.trim(), type.id, finish);
        await refresh();
        onCreated(c);
      }
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const unavailable = kind === "numismatic" && region !== "us";
  const ready = kind === "bullion" || (kind === "numismatic" && !unavailable && type != null);

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="modal new-collection-modal" role="dialog" aria-modal="true" aria-label="New collection" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>New Collection</h2>

        <div className="field">
          <span>What are you collecting?</span>
          <div className="segmented kind-choice" role="radiogroup" aria-label="Kind of collection">
            {(
              [
                ["numismatic", "Numismatic", "Graded and raw coins, by date and mint"],
                ["bullion", "Bullion", "Bars, rounds, rolls and junk silver, by metal"],
              ] as const
            ).map(([k, label, hint]) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k} className={`seg ${kind === k ? "active" : ""}`} onClick={() => setKind(k)}>
                <strong>{label}</strong>
                <span className="small">{hint}</span>
              </button>
            ))}
          </div>
        </div>

        {kind === "numismatic" && (
          <>
            <label className="field">
              <span>Coins from</span>
              <select value={region} onChange={(e) => setRegion(e.target.value as Region)}>
                {REGIONS.map(([r, label]) => (
                  <option key={r} value={r}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {unavailable ? (
              <p className="notice small">
                {region === "world" ? "World coins" : "Ancient coins"} aren't available yet, but they're coming soon. For now,
                TrackMyCoins covers U.S. coins.
              </p>
            ) : (
              <>
                <label className="field">
                  <span>Category</span>
                  <select
                    value={category}
                    onChange={(e) => {
                      setCategory(e.target.value);
                      chooseType(null);
                    }}
                  >
                    <option value="" disabled>
                      Choose a category…
                    </option>
                    {categories.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                {category && (
                  <label className="field">
                    <span>Series</span>
                    <select value={typeId ?? ""} onChange={(e) => chooseType(Number(e.target.value) || null)}>
                      <option value="" disabled>
                        Choose a series…
                      </option>
                      {coinTypes
                        .filter((t) => t.category === category)
                        .map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.plural}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                {type && type.finishes.length > 1 && (
                  <div className="field">
                    <span>Finish</span>
                    <div className="segmented" role="radiogroup" aria-label="Finish">
                      {type.finishes.map((f) => (
                        <button key={f.code} type="button" role="radio" aria-checked={finish === f.code} className={`seg ${finish === f.code ? "active" : ""}`} onClick={() => setFinish(f.code)}>
                          {FINISH_CHOICE[f.code]}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {kind === "bullion" && (
          <div className="field">
            <span>Metal</span>
            <div className="segmented" role="radiogroup" aria-label="Metal">
              {(Object.keys(METAL_LABEL) as Metal[]).map((m) => (
                <button key={m} type="button" role="radio" aria-checked={metal === m} className={`seg metal-${m} ${metal === m ? "active" : ""}`} onClick={() => setMetal(m)}>
                  {METAL_LABEL[m]}
                </button>
              ))}
            </div>
            <span className="muted small">Bars, rounds, coins, rolls and tubes, valued at today's spot price.</span>
          </div>
        )}

        {ready && (
          <label className="field">
            <span>Name</span>
            <input
              value={shownName}
              onChange={(e) => {
                setName(e.target.value);
                setNameTouched(true);
              }}
              required
              maxLength={200}
            />
          </label>
        )}

        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy || !ready || !shownName.trim()}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

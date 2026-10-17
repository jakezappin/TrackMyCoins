import { useMemo, useState } from "react";
import { api, type Collection, type Finish } from "../api";
import { useApp } from "../App";

interface Props {
  /** Pre-select a collection type, e.g. "kennedy-half-dollars-proof". */
  initialType?: string;
  onClose: () => void;
  onCreated: (c: Collection) => void;
}

const FINISH_WORD: Record<Finish, string> = { MS: "", PR: " Proof", SPR: " Silver Proof" };

export default function NewCollectionDialog({ initialType, onClose, onCreated }: Props) {
  const { coinTypes, collections, refresh } = useApp();

  // Every (series, finish) pair, grouped by category for the dropdown.
  const options = useMemo(
    () =>
      coinTypes.flatMap((t) =>
        t.finishes.map((f) => ({ type: t, finish: f, value: f.collection_type_slug, label: f.collection_type_label })),
      ),
    [coinTypes],
  );
  const groups = useMemo(() => {
    const g = new Map<string, typeof options>();
    for (const o of options) g.set(o.type.category, [...(g.get(o.type.category) ?? []), o]);
    return [...g.entries()];
  }, [options]);

  const [typeSlug, setTypeSlug] = useState(initialType ?? "");
  const selected = options.find((o) => o.value === typeSlug);

  const defaultName = (o: (typeof options)[number]) => {
    const n = collections.filter((c) => c.collection_type_slug === o.value).length + 1;
    return `${o.type.name}${FINISH_WORD[o.finish.code]} Collection ${n}`;
  };
  const [name, setName] = useState(selected ? defaultName(selected) : "");
  const [nameTouched, setNameTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function chooseType(value: string) {
    setTypeSlug(value);
    const o = options.find((x) => x.value === value);
    // Keep a name the user typed; otherwise suggest one for the new type.
    if (o && !nameTouched) setName(defaultName(o));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const c = await api.createCollection(name, selected.type.id, selected.finish.code);
      await refresh();
      onCreated(c);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>New Collection</h2>
        <label className="field">
          <span>Type of collection</span>
          <select value={typeSlug} onChange={(e) => chooseType(e.target.value)} required autoFocus={!initialType}>
            <option value="" disabled>
              Choose a type…
            </option>
            {groups.map(([category, opts]) => (
              <optgroup key={category} label={category}>
                {opts.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Name</span>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setNameTouched(true);
            }}
            placeholder={selected ? defaultName(selected) : "e.g. Peace Dollar Collection 2"}
            required
            maxLength={200}
            autoFocus={Boolean(initialType)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy || !selected || !name.trim()}>
            Create
          </button>
        </div>
      </form>
    </div>
  );
}

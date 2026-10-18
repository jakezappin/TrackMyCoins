import { useEffect, useId, useRef, useState } from "react";
import { api, type CatalogHit } from "../api";

/** "1878-S Morgan", "1962-S Roosevelt Proof", "1880/79-CC": pick the coin from the catalog and the form fills in its
 * collection, date, mint, variety, designation and PCGS #. */
export default function CoinSearch({ onPick }: { onPick: (h: CatalogHit) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<CatalogHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  // The term the hits are for, and an Enter pressed before they arrived: it picks the best match for what was
  // typed, never one left from the previous search (and never submits the coin form).
  const hitsFor = useRef("");
  const enterPending = useRef(false);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 3) {
      setHits([]);
      return;
    }
    let live = true;
    setLoading(true);
    const t = window.setTimeout(() => {
      api
        .catalogSearch(term)
        .then((h) => {
          if (!live) return;
          hitsFor.current = term;
          setHits(h);
          setActive(0);
          setOpen(true);
          if (enterPending.current) {
            enterPending.current = false;
            pick(h[0]);
          }
        })
        .catch(() => live && setHits([]))
        .finally(() => live && setLoading(false));
    }, 200);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [q]);

  // Close when clicking elsewhere.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function pick(h: CatalogHit | undefined) {
    enterPending.current = false;
    if (!h) return;
    onPick(h);
    setPicked(`${h.label}${h.detail ? ` · ${h.detail}` : ""}`);
    setQ("");
    setHits([]);
    setOpen(false);
  }

  const showList = open && q.trim().length >= 3;
  return (
    <div className="coin-search catalog-search" ref={box}>
      <label className="field">
        <span>Find the coin</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => hits.length && setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, hits.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault(); // Enter here never submits the coin form
              if (hitsFor.current === q.trim()) pick(hits[active]);
              else if (q.trim().length >= 3) enterPending.current = true;
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder="Type a date and series, e.g. 1878-S Morgan, 1962-S Roosevelt Proof, 1880/79-CC"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          maxLength={100}
        />
      </label>
      {showList && (
        <ul className="coin-search-hits catalog-hits" id={listId} role="listbox">
          {hits.length === 0 && !loading && <li className="muted small">No matches. Add a date and series, e.g. 1881-S Morgan.</li>}
          {hits.map((h, i) => (
            <li
              key={h.gsid}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(h);
              }}
            >
              <span>
                <strong>{h.label}</strong>
                {h.detail && <span className="muted"> · {h.detail}</span>}
                <span className="small muted catalog-hit-col">
                  {h.collection_name ? `→ ${h.collection_name}` : `→ new ${h.series_name}${h.finish === "PR" ? " Proof" : h.finish === "SPR" ? " Silver Proof" : ""} collection`}
                </span>
              </span>
              <span className="mono small muted">{h.pcgs_number ? `PCGS #${h.pcgs_number}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
      {picked && !showList && (
        <p className="small muted">
          Filled in from <strong>{picked}</strong>. Now add the grade, designation and cert number.
        </p>
      )}
    </div>
  );
}

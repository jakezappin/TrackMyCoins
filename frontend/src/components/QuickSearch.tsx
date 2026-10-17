import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type SearchHit } from "../api";
import { useApp } from "../App";
import { coinPath, dateMint, gradeLabel, metalFor, serviceLabel } from "../format";
import CoinPlaceholder from "./CoinPlaceholder";

/** Search the user's coins and jump straight to one. Press "/" anywhere to focus. */
export default function QuickSearch() {
  const navigate = useNavigate();
  const { coinTypes } = useApp();
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);

  // "/" focuses the box (unless you're already typing somewhere).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) && !t.isContentEditable) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Debounced search as you type.
  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setHits([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    let cancelled = false;
    const t = setTimeout(() => {
      api
        .searchCoins(term)
        .then((h) => {
          if (cancelled) return;
          setHits(h);
          setActive(0);
          setOpen(true);
        })
        .catch(() => !cancelled && setHits([]))
        .finally(() => !cancelled && setLoading(false));
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [q]);

  function go(hit: SearchHit | undefined) {
    if (!hit) return;
    setOpen(false);
    setQ("");
    navigate(coinPath(hit.coin.inventory_number));
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(hits[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  const showList = open && q.trim().length > 0;

  return (
    <div className="qs" onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <div className="qs-box">
        <svg viewBox="0 0 24 24" className="qs-icon" aria-hidden>
          <circle cx="11" cy="11" r="6.5" />
          <path d="m16 16 4.5 4.5" />
        </svg>
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => hits.length && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Find a coin: inventory #, cert, 1881-S, Boone, notes…"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label="Search your coins"
        />
        <kbd className="qs-kbd" aria-hidden>
          /
        </kbd>
      </div>
      {showList && (
        <ul className="qs-list" id={listId} role="listbox">
          {hits.length === 0 ? (
            <li className="qs-empty muted">{loading ? "Searching…" : `No coins match “${q.trim()}”`}</li>
          ) : (
            hits.map((h, i) => (
              <li
                key={h.coin.id}
                role="option"
                aria-selected={i === active}
                className={`qs-hit ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => go(h)}
              >
                {h.coin.thumbnail_url ? (
                  <img src={h.coin.thumbnail_url} alt="" className="qs-thumb" />
                ) : (
                  <CoinPlaceholder className="qs-thumb ph" metal={metalFor(coinTypes, h.coin.coin_type_id)} />
                )}
                <span className="qs-main">
                  <strong>
                    {dateMint(h.coin)} {h.type_name} {gradeLabel(h.coin)}
                  </strong>
                  <span className="muted small">
                    {h.coin.inventory_number} · {serviceLabel(h.coin.grading_service)}
                    {h.coin.cert_number ? ` ${h.coin.cert_number}` : ""} · {h.collection_name}
                    {h.coin.variety ? ` · ${h.coin.variety}` : ""}
                  </span>
                </span>
                {h.coin.is_sold && <span className="tag sold">Sold</span>}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

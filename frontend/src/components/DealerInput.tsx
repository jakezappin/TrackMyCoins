import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dealer } from "../api";

let cache: Promise<Dealer[]> | null = null;
/** The user's dealers, fetched once per page load (and again after adding one). */
export function loadDealers(fresh = false): Promise<Dealer[]> {
  if (fresh || !cache) cache = api.dealers().catch(() => []);
  return cache;
}

/** "Purchased from" / "Sold to": type anything, or pick one of your dealers to link the coin to them. */
export default function DealerInput({
  text,
  dealerId,
  onChange,
  placeholder,
}: {
  text: string | null;
  dealerId: number | null;
  onChange: (text: string | null, dealerId: number | null) => void;
  placeholder?: string;
}) {
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();

  useEffect(() => {
    loadDealers().then(setDealers);
  }, []);

  const q = (text ?? "").trim().toLowerCase();
  const hits = dealers
    .filter((d) => !q || [d.business, d.contact_name].some((n) => n && n.toLowerCase().includes(q)))
    .slice(0, 6);
  const linked = dealerId != null ? dealers.find((d) => d.id === dealerId) : null;

  function pick(d: Dealer) {
    onChange(d.display_name, d.id);
    setOpen(false);
  }

  return (
    <div className="dealer-input">
      <input
        value={text ?? ""}
        placeholder={placeholder}
        maxLength={200}
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls={listId}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          // Typing unlinks: the text is just text unless a dealer is picked.
          onChange(e.target.value || null, null);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (!open || !hits.length) return;
          if (e.key === "ArrowDown") (e.preventDefault(), setActive((a) => Math.min(a + 1, hits.length - 1)));
          else if (e.key === "ArrowUp") (e.preventDefault(), setActive((a) => Math.max(a - 1, 0)));
          else if (e.key === "Enter" && q) (e.preventDefault(), pick(hits[active]));
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {linked && (
        <small className="dealer-linked">
          🏪 Linked to <Link to={`/dealers/${linked.id}`}>{linked.display_name}</Link>
        </small>
      )}
      {open && hits.length > 0 && !linked && (
        <ul className="coin-search-hits dealer-hits" id={listId} role="listbox">
          {hits.map((d, i) => (
            <li
              key={d.id}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(d);
              }}
            >
              <span>
                🏪 {d.display_name}
                {d.business && d.contact_name ? <span className="muted"> · {d.contact_name}</span> : null}
              </span>
              <span className="small muted">dealer</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

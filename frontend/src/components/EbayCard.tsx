import { useCallback, useEffect, useState } from "react";
import { api, type EbayListings } from "../api";
import { money } from "../format";

const COLLAPSE_KEY = "ebay-card-collapsed";

// Asked once per page load: is eBay set up on the server? (The card stays hidden until it is.)
let enabled: Promise<boolean> | null = null;
const ebayEnabled = () => (enabled ??= api.features().then((f) => f.ebay).catch(() => false));

function timeLeft(iso: string | null): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "ended";
  const h = Math.floor(ms / 3600000);
  return h >= 48 ? `${Math.floor(h / 24)}d left` : h >= 1 ? `${h}h left` : `${Math.max(1, Math.floor(ms / 60000))}m left`;
}

/** Listings for this coin's date, mint, service and grade on eBay right now (asking prices, not sales). */
export default function EbayCard({ inv }: { inv: string }) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    ebayEnabled().then(setOn);
  }, []);
  return on ? <EbayListingsCard inv={inv} /> : null;
}

function EbayListingsCard({ inv }: { inv: string }) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [data, setData] = useState<EbayListings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await api.ebayListings(inv));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [inv]);

  // Only ask eBay when the card is open.
  useEffect(() => {
    if (!collapsed && !data && !busy && !error) load();
  }, [collapsed, data, busy, error, load]);

  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
      } catch {
        // Remembering is only a convenience.
      }
      return !c;
    });

  const s = data?.configured ? data.stats : null;
  return (
    <section className={`card ebay-card${collapsed ? " collapsed" : ""}`}>
      <div className="section-head">
        <button type="button" className="collapse-toggle" onClick={toggle} aria-expanded={!collapsed}>
          <span className="chev" aria-hidden="true">
            ▾
          </span>
          <h2>For sale on eBay now</h2>
        </button>
        {!collapsed && data?.search_url && (
          <a className="btn" href={data.search_url} target="_blank" rel="noreferrer">
            See on eBay ↗
          </a>
        )}
      </div>
      {collapsed ? (
        s && s.count > 0 ? (
          <p className="muted small collapsed-summary">
            {s.count} listing{s.count === 1 ? "" : "s"}
            {s.low != null ? ` · Buy It Now from ${money(s.low)}` : ""}
          </p>
        ) : null
      ) : (
        <>
          {busy && !data && <p className="muted small">Checking eBay…</p>}
          {error && (
            <p className="error small">
              {error}{" "}
              <button type="button" className="link-btn" onClick={load}>
                Try again
              </button>
            </p>
          )}
          {data && !data.configured && (
            <p className="muted small">eBay listings aren't set up on this server yet. Use See on eBay ↗ to search there.</p>
          )}
          {data?.configured && (
            <>
              <p className="muted small">
                Current asking prices for “{data.query}”, not sales. Lots, “details” coins, other grades and other
                designations are left out.
              </p>
              {s && s.count > 0 ? (
                <>
                  <dl className="market-stats">
                    <div>
                      <dt>Lowest Buy It Now</dt>
                      <dd>{money(s.low)}</dd>
                    </div>
                    <div>
                      <dt>Median asking</dt>
                      <dd>{money(s.median)}</dd>
                    </div>
                    <div>
                      <dt>Listings</dt>
                      <dd>
                        {s.count}
                        {s.count > s.buy_it_now_count && (
                          <span className="muted small"> · {s.count - s.buy_it_now_count} auction{s.count - s.buy_it_now_count === 1 ? "" : "s"}</span>
                        )}
                      </dd>
                    </div>
                  </dl>
                  <ul className="ebay-list">
                    {data.items.map((it) => (
                      <li key={it.url ?? it.title}>
                        <a href={it.url ?? data.search_url} target="_blank" rel="noreferrer" className="ebay-item">
                          {it.image ? <img src={it.image} alt="" loading="lazy" /> : <span className="ebay-noimg" />}
                          <span className="ebay-title">{it.title}</span>
                          <span className="ebay-price">
                            <strong>{money(it.price)}</strong>
                            <span className="small muted">
                              {it.kind === "auction"
                                ? `${it.bids ?? 0} bid${it.bids === 1 ? "" : "s"}${it.ends ? ` · ${timeLeft(it.ends)}` : ""}`
                                : it.best_offer
                                  ? "Buy It Now · offers"
                                  : "Buy It Now"}
                            </span>
                            {it.cac && <span className="tag cac-green">CAC</span>}
                          </span>
                        </a>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="muted small">No matching listings right now.</p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

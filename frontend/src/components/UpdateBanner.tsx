import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

/** The script this page loaded: /assets/index-<hash>.js. */
function loadedScript(): string | null {
  const s = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/index-"]');
  return s ? new URL(s.src, location.href).pathname : null;
}

/** A page left open keeps running the version it loaded. When a newer one has been deployed, say so (checked every
 * few minutes and on moving between pages) so fixes reach open tabs. */
export default function UpdateBanner() {
  const [stale, setStale] = useState(false);
  const loc = useLocation();
  const [lastCheck, setLastCheck] = useState(0);

  async function check() {
    const mine = loadedScript();
    if (!mine || stale) return; // the dev server has no hashed bundle
    try {
      const html = await fetch("/", { cache: "no-store", credentials: "same-origin" }).then((r) => r.text());
      const live = /\/assets\/index-[\w-]+\.js/.exec(html)?.[0];
      if (live && live !== mine) setStale(true);
    } catch {
      // offline or mid-deploy: try again later
    }
    setLastCheck(Date.now());
  }

  useEffect(() => {
    const t = window.setInterval(check, 5 * 60_000);
    return () => window.clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (Date.now() - lastCheck > 60_000) check();
  }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!stale) return null;
  return (
    <div className="update-banner" role="status">
      TrackMyCoins was updated. Refresh to get the latest.
      <button className="btn small" onClick={() => location.reload()}>
        Refresh
      </button>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { ngcBookmarklet } from "../ngcButton";

const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isAndroid = /Android/.test(navigator.userAgent);

/** How to install the "Add to TrackMyCoins" bookmark for NGC coins. */
export default function NgcButtonPage() {
  const code = useMemo(() => ngcBookmarklet(window.location.origin), []);
  const link = useRef<HTMLAnchorElement>(null);
  const [copied, setCopied] = useState(false);

  // React won't render javascript: links itself, so set it directly.
  useEffect(() => {
    link.current?.setAttribute("href", code);
  }, [code]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this:", code);
    }
  }

  const desktop = (
    <section className="card form-section" key="desktop">
      <h2>On a computer (Chrome, Edge, Safari, Firefox)</h2>
      <ol className="steps">
        <li>
          Show your bookmarks bar: <strong>Cmd+Shift+B</strong> on a Mac or <strong>Ctrl+Shift+B</strong> on Windows (in
          Safari: View → Show Favorites Bar).
        </li>
        <li>
          Drag this button onto the bookmarks bar:{" "}
          <a ref={link} className="btn btn-primary ngc-bookmarklet" onClick={(e) => e.preventDefault()} draggable>
            ＋ Add to TrackMyCoins
          </a>
        </li>
        <li>Open any coin's NGC cert page and click the bookmark.</li>
      </ol>
    </section>
  );
  const ios = (
    <section className="card form-section" key="ios">
      <h2>On iPhone or iPad (Safari)</h2>
      <ol className="steps">
        <li>
          <button type="button" className="btn btn-primary" onClick={copy}>
            {copied ? "Copied ✓" : "Copy the button code"}
          </button>
        </li>
        <li>
          Bookmark this page: tap <strong>Share</strong> → <strong>Add Bookmark</strong>, name it{" "}
          <strong>Add to TrackMyCoins</strong>, and save.
        </li>
        <li>
          Tap the <strong>Bookmarks</strong> icon → <strong>Edit</strong> → the new bookmark. Delete its address and paste
          the copied code in its place. Tap <strong>Done</strong>.
        </li>
        <li>
          On a coin's NGC cert page, tap <strong>Bookmarks</strong> → <strong>Add to TrackMyCoins</strong>.
        </li>
      </ol>
    </section>
  );
  const android = (
    <section className="card form-section" key="android">
      <h2>On Android (Chrome)</h2>
      <ol className="steps">
        <li>
          <button type="button" className="btn btn-primary" onClick={copy}>
            {copied ? "Copied ✓" : "Copy the button code"}
          </button>
        </li>
        <li>
          Bookmark this page (⋮ → ☆), then edit the bookmark: name it <strong>Add to TrackMyCoins</strong> and paste the
          code as its URL.
        </li>
        <li>
          On a coin's NGC cert page, tap the address bar, type <strong>Add to TrackMyCoins</strong>, and tap the bookmark
          in the suggestions.
        </li>
      </ol>
    </section>
  );

  return (
    <div className="page ngc-button-page">
      <div className="page-head">
        <div>
          <h1>Add NGC coins in one tap</h1>
          <p className="muted">
            NGC doesn't let other sites look up its coins, so this bookmark works from NGC's own page in your browser.
            In the add-coin form, choose NGC, enter the cert and grade, and click <strong>Open on NGC</strong>. On NGC's
            page, click <strong>Add to TrackMyCoins</strong>: you're back in the same tab with your form as you left
            it, plus NGC's photos (both sides, full size), cert, grade, date and designation.
          </p>
        </div>
      </div>
      {isIOS ? [ios, desktop, android] : isAndroid ? [android, desktop, ios] : [desktop, ios, android]}
      <p className="muted small">
        Find a coin's NGC page with NGC's{" "}
        <a href="https://www.ngccoin.com/certlookup/" target="_blank" rel="noreferrer">
          cert lookup ↗
        </a>{" "}
        or the <strong>Verify ↗</strong> button on an NGC coin in TrackMyCoins. If the coin is already in your collection,
        you'll be offered to add NGC's photos to it instead.
      </p>
    </div>
  );
}

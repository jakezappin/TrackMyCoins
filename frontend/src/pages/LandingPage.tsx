import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Logo from "../components/Logo";

const FEATURES = [
  {
    title: "Cert Lookup In One Step",
    body: "Type a PCGS cert number and the year, mint, grade, designation, photos and CAC sticker fill in for you.",
    icon: (
      <path d="M4 7h16M4 12h10M4 17h7m9-2.5 2.5 2.5M16 14.5a3.5 3.5 0 1 0 7 0 3.5 3.5 0 0 0-7 0Z" />
    ),
  },
  {
    title: "Know What's Missing",
    body: "Collection Status lists every date and mint in the series, earliest first, with your coins beside each. Type sets too, like the 23-coin Gold Type Set and classic commemoratives. One click shows only the holes.",
    icon: <path d="M5 6h3m-3 6h3m-3 6h3M11 6h9m-9 6h9m-9 6h9M4.5 12l1 1 2-2" />,
  },
  {
    title: "Real Values, Not Guesses",
    body: "Pull CPG retail from Greysheet and the PCGS Price Guide, keep a price history, and see totals and estimated wholesale for every collection.",
    icon: <path d="M4 19V5m0 14h16M8 15l3-4 3 2 5-6" />,
  },
  {
    title: "Recent Auction Sales",
    body: "The last ten auction results for your coin and grade, charted against the price guides (buyer's premium included), with links to every lot.",
    icon: <path d="M5 17l4-5 4 3 6-8M5 7h.01M9 12h.01M13 15h.01M19 7h.01" />,
  },
  {
    title: "Every Major U.S. Series",
    body: "Half cents to Ike dollars, classic commemoratives, early and classic gold from Draped Bust to Saint-Gaudens, the $4 Stella, Silver and Gold Eagles and Gold Buffalos. Business strikes, proofs and silver proofs.",
    icon: <path d="M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 3v10m-3-7h6" />,
  },
  {
    title: "Collector Details That Matter",
    body: "CAC green and gold beans, Rattlers, Fatties, OGH, Soapboxes, GSA holders, toning, VAMs, raw coins. Plus Excel export and a sold list with profit and loss.",
    icon: <path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h3" />,
  },
];

const STATUS_ROWS: [string, string | null][] = [
  ["1878 8TF", "MS64 · CAC"],
  ["1878 7TF, Reverse of 1878", "MS62"],
  ["1878 7/8TF, Strong", null],
  ["1878-CC", "MS65 · GSA"],
  ["1878-S", "MS64"],
  ["1879", null],
  ["1879-CC", null],
  ["1879-O", "MS63"],
];

function StatusPreview() {
  return (
    <div className="lp-panel">
      <div className="lp-panel-head">
        <strong>Collection Status</strong>
        <span className="muted small">Morgan Dollars – MS</span>
      </div>
      <div className="lp-progress">
        <span>
          <strong>42 of 99</strong> dates filled
        </span>
        <span className="lp-pct">42%</span>
      </div>
      <div className="progress">
        <div className="progress-bar" style={{ width: "42%" }} />
      </div>
      <ul className="lp-status">
        {STATUS_ROWS.map(([label, coin]) => (
          <li key={label} className={coin ? "have" : "missing"}>
            <span className="lp-check">{coin ? "✓" : ""}</span>
            <span className="lp-date">{label}</span>
            {coin ? <span className="lp-chip">{coin}</span> : <span className="lp-missing">Missing</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Sample sales for the preview chart (price in dollars by month index).
const SALES = [
  [0, 288],
  [1, 336],
  [2, 336],
  [3, 268],
  [3.3, 244],
  [4, 390],
  [5, 317],
];

function MarketPreview() {
  const W = 360;
  const H = 230;
  const x = (m: number) => 36 + (m / 5) * (W - 110);
  const y = (v: number) => 12 + (1 - (v - 200) / 250) * (H - 40);
  return (
    <div className="lp-panel">
      <div className="lp-panel-head">
        <strong>PCGS market</strong>
        <span className="muted small">1878 8TF · MS62</span>
      </div>
      <div className="lp-stats">
        <div>
          <span>PCGS Guide</span>
          <strong>$335</strong>
        </div>
        <div>
          <span>CPG</span>
          <strong>$325</strong>
        </div>
        <div>
          <span>Avg. last 7</span>
          <strong>$311</strong>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="lp-chart" role="img" aria-label="Sample auction price chart">
        {[200, 250, 300, 350, 400, 450].map((t) => (
          <g key={t}>
            <line x1={36} x2={W - 74} y1={y(t)} y2={y(t)} className="lp-grid" />
            <text x={30} y={y(t)} dy="0.32em" textAnchor="end" className="lp-axis">
              ${t}
            </text>
          </g>
        ))}
        <line x1={36} x2={W - 74} y1={y(335)} y2={y(335)} className="lp-ref" strokeDasharray="6 4" />
        <line x1={36} x2={W - 74} y1={y(325)} y2={y(325)} className="lp-ref" strokeDasharray="2 4" />
        <text x={W - 68} y={y(335) - 4} className="lp-ref-label">
          Guide
        </text>
        <text x={W - 68} y={y(325) + 9} className="lp-ref-label">
          CPG
        </text>
        {SALES.map(([m, v], i) => (
          <circle key={i} cx={x(m)} cy={y(v)} r={5} className="lp-dot" />
        ))}
        {["Jan", "Mar", "May"].map((mo, i) => (
          <text key={mo} x={x(i * 2)} y={H - 6} textAnchor="middle" className="lp-axis">
            {mo}
          </text>
        ))}
      </svg>
    </div>
  );
}

export default function LandingPage() {
  // Counts come from the server so they stay right as series are added.
  const [stats, setStats] = useState({ series: 52, collection_types: 103 });
  useEffect(() => {
    api.publicStats().then(setStats).catch(() => undefined);
  }, []);

  return (
    <div className="landing">
      <header className="lp-hero">
        <nav className="lp-nav">
          <Logo size={34} tone="light" />
          <div className="lp-nav-links">
            <Link to="/login" className="lp-link">
              Log in
            </Link>
            <Link to="/signup" className="btn lp-btn-gold">
              Create account
            </Link>
          </div>
        </nav>

        <div className="lp-hero-body">
          <div className="lp-hero-copy">
            <p className="lp-eyebrow">For collectors of U.S. coins</p>
            <h1>
              Every date.
              <br />
              Every mint.
              <br />
              <span className="lp-gold">Every slab.</span>
            </h1>
            <p className="lp-lede">
              TrackMyCoins catalogs your collection by date and mint, shows exactly which coins you're missing, and keeps
              CPG, PCGS and auction values up to date.
            </p>
            <div className="lp-ctas">
              <Link to="/signup" className="btn lp-btn-gold lp-btn-lg">
                Create your account
              </Link>
              <Link to="/login" className="btn lp-btn-ghost lp-btn-lg">
                Log in
              </Link>
            </div>
            <p className="lp-note">Invite only for now. You'll need an invite code to register.</p>
          </div>

          <div className="lp-coins" aria-hidden>
            <img className="lp-coin c1" src="/img/coins/morgan-1889p-obverse.webp" alt="" width={640} height={640} />
            <img className="lp-coin c2" src="/img/coins/morgan-1880s-reverse.webp" alt="" width={640} height={640} />
            <img className="lp-coin c3" src="/img/coins/morgan-1879s-obverse.webp" alt="" width={640} height={640} />
            <div className="lp-float">
              <span className="lp-float-check">✓</span>
              <div>
                <strong>1879-S Morgan Dollar</strong>
                <span>NGC MS67+ · in your collection</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="lp-strip">
        <div>
          <strong>{stats.series}</strong>
          <span>U.S. coin series</span>
        </div>
        <div>
          <strong>{stats.collection_types}</strong>
          <span>collection types (MS, Proof &amp; Silver Proof)</span>
        </div>
        <div>
          <strong>23</strong>
          <span>gold types in the Gold Type Set</span>
        </div>
        <div>
          <strong>10</strong>
          <span>photos per coin</span>
        </div>
      </section>

      <section className="lp-section">
        <h2>Built The Way Collectors Actually Collect</h2>
        <div className="lp-features">
          {FEATURES.map((f) => (
            <article key={f.title} className="lp-feature">
              <svg viewBox="0 0 24 24" className="lp-icon" aria-hidden>
                {f.icon}
              </svg>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-section lp-showcase">
        <div className="lp-showcase-copy">
          <h2>See The Holes. Watch The Market.</h2>
          <p>
            Work through a set from the earliest date to the latest, with your best grade beside each one. Then check
            how the coins you own are actually selling at auction, next to the CPG and PCGS price guides.
          </p>
        </div>
        <div className="lp-previews">
          <StatusPreview />
          <MarketPreview />
        </div>
      </section>

      <section className="lp-cta">
        <Logo size={40} tone="light" />
        <h2>Start Tracking Your Collection</h2>
        <p>Have an invite code? Create your account in under a minute.</p>
        <div className="lp-ctas">
          <Link to="/signup" className="btn lp-btn-gold lp-btn-lg">
            Create your account
          </Link>
          <Link to="/login" className="btn lp-btn-ghost lp-btn-lg">
            Log in
          </Link>
        </div>
      </section>

      <footer className="lp-footer">
        <span>© {new Date().getFullYear()} TrackMyCoins</span>
        <span>
          Values from Greysheet (CPG) and PCGS. Not affiliated with PCGS, NGC, CAC, ANACS or CDN Publishing. Coin
          photos: Wikimedia Commons, public domain.
        </span>
      </footer>
    </div>
  );
}

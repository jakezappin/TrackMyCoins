import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type GradingAddon,
  type GradingCatalog,
  type GradingKind,
  type GradingResult,
  type SearchHit,
  type Submission,
  type SubmissionCoin,
  type SubmissionIn,
} from "../api";
import AttachmentsCard from "../components/AttachmentsCard";
import { STATUS_LABEL, submissionTitle, TurnaroundBar } from "../components/SubmissionCard";
import { coinPath, DETAILS_PROBLEMS, money, parseMoney, shortDate, todayISO } from "../format";
import { COMPANIES } from "./GradingPage";

const PREFIXES = ["MS", "PR", "SP", "AU", "XF", "VF", "F", "VG", "G", "AG", "FR", "PO"];

/** A tracking number's carrier page (UPS 1Z..., FedEx 12/15 digits, USPS otherwise, incl. registered RE...US). */
export function trackingUrl(n: string): string {
  const t = n.replace(/\s/g, "").toUpperCase();
  if (t.startsWith("1Z")) return `https://www.ups.com/track?tracknum=${encodeURIComponent(t)}`;
  if (/^\d{12}$|^\d{15}$/.test(t)) return `https://www.fedex.com/fedextrack/?trknbr=${encodeURIComponent(t)}`;
  return `https://tools.usps.com/go/TrackConfirmAction?tLabels=${encodeURIComponent(t)}`;
}

type Form = {
  name: string;
  company: SubmissionIn["company"];
  kind: GradingKind;
  tier_key: string;
  tier_name: string;
  tier_fee: string;
  tier_max_value: string;
  turnaround_days: string;
  business_days: boolean;
  addons: GradingAddon[];
  order_number: string;
  tracking_out: string;
  tracking_back: string;
  date_sent: string;
  date_received: string;
  date_shipped_back: string;
  date_returned: string;
  grading_paid: string;
  shipping_paid: string;
  notes: string;
};

const toForm = (s: Submission): Form => ({
  name: s.name ?? "",
  company: s.company,
  kind: s.kind,
  tier_key: s.tier_key ?? "",
  tier_name: s.tier_name ?? "",
  tier_fee: s.tier_fee ?? "",
  tier_max_value: s.tier_max_value ?? "",
  turnaround_days: s.turnaround_days != null ? String(s.turnaround_days) : "",
  business_days: s.business_days,
  addons: s.addons ?? [],
  order_number: s.order_number ?? "",
  tracking_out: s.tracking_out ?? "",
  tracking_back: s.tracking_back ?? "",
  date_sent: s.date_sent ?? "",
  date_received: s.date_received ?? "",
  date_shipped_back: s.date_shipped_back ?? "",
  date_returned: s.date_returned ?? "",
  grading_paid: s.grading_paid ?? "",
  shipping_paid: s.shipping_paid ?? "",
  notes: s.notes ?? "",
});

export default function SubmissionPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [sub, setSub] = useState<Submission | null>(null);
  const [catalog, setCatalog] = useState<GradingCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);

  useEffect(() => {
    let live = true;
    Promise.all([api.submission(Number(id)), api.gradingCatalog()])
      .then(([s, c]) => {
        if (!live) return;
        setSub(s);
        setCatalog(c);
      })
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [id]);

  if (error && !sub) return <div className="page error">{error}</div>;
  if (!sub || !catalog) return <div className="page muted">Loading…</div>;
  const pending = sub.coins.filter((c) => c.outcome === "pending");

  async function remove() {
    if (!sub) return;
    const n = sub.coins.filter((c) => c.outcome === "pending").length;
    if (!confirm(`Delete submission ${submissionTitle(sub)}?${n ? ` Its ${n} coin${n === 1 ? "" : "s"} go back to In Inventory.` : ""}`)) return;
    try {
      await api.deleteSubmission(sub.id);
      navigate("/grading");
    } catch (e) {
      alert(`Couldn't delete: ${(e as Error).message}`);
    }
  }

  return (
    <div className="page submission-page">
      <Link to="/grading" className="btn small back-link">
        ← Grading Tracker
      </Link>
      <div className="page-head">
        <div>
          <h1>
            {submissionTitle(sub)} <span className={`status-pill ${sub.progress.status}`}>{STATUS_LABEL[sub.progress.status]}</span>
          </h1>
          <p className="muted small">
            {sub.company_label}
            {sub.tier_name ? ` · ${sub.tier_name}` : ""} · {sub.kind_label} · {sub.coin_count} coin{sub.coin_count === 1 ? "" : "s"}
          </p>
        </div>
        <div className="row">
          {pending.length > 0 && (
            <button className="btn btn-primary" onClick={() => setRecording(true)}>
              Record results
            </button>
          )}
          <button className="btn danger" onClick={remove}>
            Delete
          </button>
        </div>
      </div>

      <section className="card">
        <h2>Turnaround</h2>
        <TurnaroundBar p={sub.progress} />
        {!sub.turnaround_days && <p className="muted small">Pick a service tier (or enter its turnaround days) to see the color tracker.</p>}
      </section>

      <CoinsCard sub={sub} onChange={setSub} />
      <DetailsForm sub={sub} catalog={catalog} onSaved={setSub} />
      <AttachmentsCard inventoryNumber={String(sub.id)} kind="grading" />

      {recording && (
        <ResultsDialog
          sub={sub}
          outcomes={catalog.outcomes}
          onClose={() => setRecording(false)}
          onSaved={(s) => {
            setSub(s);
            setRecording(false);
          }}
        />
      )}
    </div>
  );
}

// ---- Details: tier, dates, tracking, costs ------------------------------------------------------------------

function DetailsForm({ sub, catalog, onSaved }: { sub: Submission; catalog: GradingCatalog; onSaved: (s: Submission) => void }) {
  const [form, setForm] = useState<Form>(() => toForm(sub));
  const baseline = useRef(JSON.stringify(toForm(sub)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const f = toForm(sub);
    setForm(f);
    baseline.current = JSON.stringify(f);
  }, [sub]);
  const dirty = JSON.stringify(form) !== baseline.current;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => {
    setSaved(false);
    setForm((f) => ({ ...f, [k]: v }));
  };

  const kinds = (form.company === "CAC" ? ["sticker"] : Object.keys(catalog.kinds).filter((k) => k !== "sticker")) as GradingKind[];
  const ofKind = catalog.tiers.filter((t) => t.company === form.company && (t.kind === form.kind || (form.company === "CAC" && t.kind === "sticker")));
  // Graders without separate crossover / regrade tiers charge their grading tiers for them.
  const tiers = ofKind.length || !["crossover", "regrade"].includes(form.kind)
    ? ofKind
    : catalog.tiers.filter((t) => t.company === form.company && t.kind === "grading");
  const addons = catalog.addons.filter((a) => a.company === form.company);
  const orderFees = catalog.order_fees.filter((f) => f.company === form.company);

  function pickTier(key: string) {
    const t = catalog.tiers.find((x) => x.key === key);
    setSaved(false);
    setForm((f) =>
      t
        ? {
            ...f,
            tier_key: t.key,
            tier_name: t.name,
            tier_fee: t.fee != null ? String(t.fee) : "",
            tier_max_value: t.max_value != null ? String(t.max_value) : "",
            turnaround_days: t.days != null ? String(t.days) : "",
            business_days: t.business_days ?? true,
          }
        : { ...f, tier_key: "", tier_name: f.tier_name },
    );
  }

  function toggleAddon(a: GradingAddon, on: boolean) {
    setSaved(false);
    setForm((f) => {
      const addons = on ? [...f.addons, { key: a.key, name: a.name, fee: a.fee, per: a.per }] : f.addons.filter((x) => x.key !== a.key);
      // NGC Fast Track halves the tier's turnaround.
      const base = catalog.tiers.find((t) => t.key === f.tier_key)?.days;
      if (a.key === "ngc-fast-track" && base) return { ...f, addons, turnaround_days: String(on ? Math.ceil(base / 2) : base) };
      return { ...f, addons };
    });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const money_ = (label: string, v: string) => {
      const r = parseMoney(v);
      if ("error" in r) throw new Error(`${label} ${r.error}.`);
      return r.value;
    };
    let body: SubmissionIn;
    try {
      const days = form.turnaround_days.trim();
      if (days && !/^\d+$/.test(days)) throw new Error("Turnaround days must be a whole number.");
      body = {
        name: form.name || null,
        company: form.company,
        kind: form.kind,
        tier_key: form.tier_key || null,
        tier_name: form.tier_name || null,
        tier_fee: money_("Fee per coin", form.tier_fee),
        tier_max_value: money_("Max value", form.tier_max_value),
        turnaround_days: days ? Number(days) : null,
        business_days: form.business_days,
        addons: form.addons,
        order_number: form.order_number || null,
        tracking_out: form.tracking_out || null,
        tracking_back: form.tracking_back || null,
        date_sent: form.date_sent || null,
        date_received: form.date_received || null,
        date_shipped_back: form.date_shipped_back || null,
        date_returned: form.date_returned || null,
        grading_paid: money_("Grading paid", form.grading_paid),
        shipping_paid: money_("Shipping & insurance", form.shipping_paid),
        notes: form.notes || null,
      };
    } catch (err) {
      setError((err as Error).message);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.updateSubmission(sub.id, body));
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const text = (k: keyof Form, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => ({
    value: form[k] as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => set(k, e.target.value as Form[typeof k]),
    ...props,
  });
  const chosen = catalog.tiers.find((t) => t.key === form.tier_key);

  return (
    <form className="card form-section submission-form" onSubmit={save}>
      <h2>Submission Details</h2>
      <div className="grid-3">
        <label className="field">
          <span>Name (optional)</span>
          <input {...text("name", { maxLength: 100, placeholder: "e.g. Morgans for NGC" })} />
        </label>
        <label className="field">
          <span>Grading company</span>
          <select
            value={form.company}
            onChange={(e) => {
              const c = e.target.value as Form["company"];
              setSaved(false);
              setForm((f) => ({ ...f, company: c, kind: c === "CAC" ? "sticker" : f.kind === "sticker" ? "grading" : f.kind, tier_key: "", addons: [] }));
            }}
          >
            {COMPANIES.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Type</span>
          <select value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as GradingKind, tier_key: "" }))} disabled={form.company === "CAC"}>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {catalog.kinds[k]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <h3 className="details-sub">Service Tier</h3>
      <div className="grid-3">
        <label className="field span-2">
          <span>Tier</span>
          <select value={form.tier_key} onChange={(e) => pickTier(e.target.value)}>
            <option value="">{tiers.length ? "Choose a tier…" : "Custom (enter below)"}</option>
            {tiers.map((t) => (
              <option key={t.key} value={t.key}>
                {t.name}
                {t.fee != null ? ` · $${t.fee}` : ""}
                {t.days != null ? ` · ${t.days} ${t.business_days ? "business " : ""}days` : ""}
              </option>
            ))}
          </select>
        </label>
        {!form.tier_key && (
          <label className="field">
            <span>Tier name</span>
            <input {...text("tier_name", { maxLength: 100, placeholder: "e.g. Economy" })} />
          </label>
        )}
      </div>
      {chosen && (chosen.turnaround_text || chosen.membership || chosen.note) && (
        <p className="muted small">
          {[chosen.turnaround_text, chosen.membership && `Needs: ${chosen.membership}`, chosen.note].filter(Boolean).join(" · ")}
          {chosen.source && (
            <>
              {" "}
              ·{" "}
              <a href={chosen.source} target="_blank" rel="noopener noreferrer">
                {form.company} fees page
              </a>
            </>
          )}
        </p>
      )}
      <div className="grid-4">
        <label className="field">
          <span>Fee per coin ($)</span>
          <input {...text("tier_fee", { inputMode: "decimal", placeholder: "0.00" })} />
        </label>
        <label className="field">
          <span>Max value per coin ($)</span>
          <input {...text("tier_max_value", { inputMode: "decimal", placeholder: "No limit" })} />
        </label>
        <label className="field">
          <span>Turnaround (days)</span>
          <input {...text("turnaround_days", { inputMode: "numeric", placeholder: "e.g. 30" })} />
        </label>
        <div className="field">
          <span>Counted in</span>
          <div className="segmented">
            <button type="button" className={`seg ${form.business_days ? "active" : ""}`} onClick={() => set("business_days", true)}>
              Business days
            </button>
            <button type="button" className={`seg ${!form.business_days ? "active" : ""}`} onClick={() => set("business_days", false)}>
              Calendar days
            </button>
          </div>
        </div>
      </div>
      {addons.length > 0 && (
        <div className="field">
          <span>Add-ons</span>
          <div className="checks addon-checks">
            {addons.map((a) => (
              <label key={a.key}>
                <input type="checkbox" checked={form.addons.some((x) => x.key === a.key)} onChange={(e) => toggleAddon(a, e.target.checked)} />{" "}
                {a.name}
                {a.fee != null ? ` (+$${a.fee}${a.per === "order" ? " per order" : " per coin"})` : ""}
              </label>
            ))}
          </div>
        </div>
      )}
      {orderFees.length > 0 && (
        <p className="muted small">
          Also charged per order: {orderFees.map((f) => `${f.name}${f.fee != null ? ` $${f.fee}` : ""}`).join(", ")}.
        </p>
      )}
      {catalog.checked && <p className="muted small">Tier list checked {shortDate(catalog.checked)}; graders change fees often, so check before sending.</p>}

      <h3 className="details-sub">Dates &amp; Tracking</h3>
      <div className="grid-4">
        <label className="field">
          <span>Date sent</span>
          <input type="date" max={todayISO()} {...text("date_sent")} />
        </label>
        <label className="field">
          <span>Received by grader</span>
          <input type="date" max={todayISO()} {...text("date_received")} />
        </label>
        <label className="field">
          <span>Shipped back</span>
          <input type="date" max={todayISO()} {...text("date_shipped_back")} />
        </label>
        <label className="field">
          <span>Returned to you</span>
          <input type="date" max={todayISO()} {...text("date_returned")} />
        </label>
      </div>
      <p className="muted small">The turnaround clock starts when the grader receives it (until then, from the date sent).</p>
      <div className="grid-3">
        <label className="field">
          <span>Grader's order / submission #</span>
          <input {...text("order_number", { maxLength: 60 })} />
        </label>
        <label className="field">
          <span>
            Tracking (to grader){" "}
            {form.tracking_out && (
              <a href={trackingUrl(form.tracking_out)} target="_blank" rel="noopener noreferrer" className="small">
                Track
              </a>
            )}
          </span>
          <input {...text("tracking_out", { maxLength: 60 })} />
        </label>
        <label className="field">
          <span>
            Tracking (back){" "}
            {form.tracking_back && (
              <a href={trackingUrl(form.tracking_back)} target="_blank" rel="noopener noreferrer" className="small">
                Track
              </a>
            )}
          </span>
          <input {...text("tracking_back", { maxLength: 60 })} />
        </label>
      </div>

      <h3 className="details-sub">Costs</h3>
      <div className="grid-3">
        <label className="field">
          <span>Grading paid ($)</span>
          <input {...text("grading_paid", { inputMode: "decimal", placeholder: sub.fees.estimate ? `est. ${sub.fees.estimate}` : "0.00" })} />
        </label>
        <label className="field">
          <span>Shipping &amp; insurance ($)</span>
          <input {...text("shipping_paid", { inputMode: "decimal", placeholder: "0.00" })} />
        </label>
        <div className="field">
          <span>Total</span>
          <strong className="total-cost">
            {money((parseFloat(form.grading_paid.replace(/[$,]/g, "")) || 0) + (parseFloat(form.shipping_paid.replace(/[$,]/g, "")) || 0))}
          </strong>
        </div>
      </div>
      {sub.fees.estimate && (
        <p className="muted small">
          Estimated from the tier: {money(sub.fees.per_coin)} per coin × {sub.coin_count} = {money(sub.fees.estimate)} (add-ons
          included). Grading costs aren't added to the coins' cost; change a coin's price paid yourself if you want them in.
        </p>
      )}
      <label className="field">
        <span>Notes</span>
        <textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} maxLength={5000} />
      </label>
      {error && <p className="error small">{error}</p>}
      <div className="row-end">
        {saved && !dirty && <span className="small ok">Saved</span>}
        <button type="button" className="btn" disabled={!dirty || busy} onClick={() => setForm(JSON.parse(baseline.current))}>
          Undo changes
        </button>
        <button className="btn btn-primary" disabled={!dirty || busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

// ---- Coins ----------------------------------------------------------------------------------------------------

function CoinsCard({ sub, onChange }: { sub: Submission; onChange: (s: Submission) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const open = !sub.date_returned;

  useEffect(() => {
    const term = q.trim();
    if (!term) return setHits([]);
    let live = true;
    const t = window.setTimeout(() => {
      api
        .searchCoins(term, 8)
        .then((h) => live && setHits(h))
        .catch(() => live && setHits([]));
    }, 150);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [q]);

  async function run(fn: () => Promise<Submission>) {
    setError(null);
    try {
      onChange(await fn());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const inSub = new Set(sub.coins.map((c) => c.coin.inventory_number));
  return (
    <section className="card">
      <div className="section-head">
        <h2>Coins</h2>
        <span className="small muted">
          Declared value {money(sub.declared_total)}
          {sub.fees.estimate ? ` · est. fees ${money(sub.fees.estimate)}` : ""}
        </span>
      </div>
      {sub.over_max_value.length > 0 && (
        <p className="error small">
          Over this tier's {money(sub.tier_max_value)} max value per coin: {sub.over_max_value.join(", ")}. Pick a higher tier
          for {sub.over_max_value.length === 1 ? "it" : "them"}.
        </p>
      )}
      {open && (
        <div className="coin-search">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Add a coin: inventory #, cert, 1881-S, Morgan…"
            aria-label="Search your coins to add"
            maxLength={100}
          />
          {hits.length > 0 && (
            <ul className="coin-search-hits">
              {hits.map((h) => {
                const c = h.coin;
                const taken = inSub.has(c.inventory_number);
                const elsewhere = c.location === "grading" && !taken;
                const sold = c.is_sold;
                return (
                  <li key={c.inventory_number}>
                    <span>
                      <strong>{c.inventory_number}</strong> {c.year}
                      {c.mint_mark !== "P" ? `-${c.mint_mark}` : ""} {h.type_name}{" "}
                      <span className="muted small">· {h.collection_name}</span>
                    </span>
                    <button
                      type="button"
                      className="btn small"
                      disabled={taken || elsewhere || sold}
                      onClick={() =>
                        run(async () => {
                          const s = await api.addSubmissionCoin(sub.id, { inventory_number: c.inventory_number });
                          setQ("");
                          return s;
                        })
                      }
                    >
                      {taken ? "Added" : elsewhere ? `At grading (#${c.grading?.number ?? "?"})` : sold ? "Sold" : "+ Add"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
      {error && <p className="error small">{error}</p>}
      {sub.coins.length === 0 ? (
        <p className="muted small">No coins yet. Search above to add coins from your collections.</p>
      ) : (
        <div className="table-scroll">
          <table className="history submission-coins">
            <thead>
              <tr>
                <th>Coin</th>
                <th>Sent as</th>
                <th>Expected</th>
                <th className="num">Declared value</th>
                <th>Result</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sub.coins.map((c) => (
                <CoinRow key={c.id} sub={sub} c={c} run={run} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CoinRow({ sub, c, run }: { sub: Submission; c: SubmissionCoin; run: (fn: () => Promise<Submission>) => void }) {
  const [expected, setExpected] = useState(c.expected_grade ?? "");
  const [declared, setDeclared] = useState(c.declared_value ?? "");
  const pending = c.outcome === "pending";
  useEffect(() => {
    setExpected(c.expected_grade ?? "");
    setDeclared(c.declared_value ?? "");
  }, [c.expected_grade, c.declared_value]);

  function save() {
    if (expected === (c.expected_grade ?? "") && declared === (c.declared_value ?? "")) return;
    const d = parseMoney(declared);
    if ("error" in d) return alert(`Declared value ${d.error}.`);
    run(() => api.editSubmissionCoin(sub.id, c.id, { expected_grade: expected || null, declared_value: d.value }));
  }

  return (
    <tr>
      <td>
        <Link to={coinPath(c.coin.inventory_number)}>
          {c.coin.year}
          {c.coin.mint_mark !== "P" ? `-${c.coin.mint_mark}` : ""} {c.coin.coin_type_name}
        </Link>
        <div className="muted small">
          {c.coin.inventory_number}
          {c.coin.variety ? ` · ${c.coin.variety}` : ""}
        </div>
      </td>
      <td className="small">{c.before?.label ?? c.coin.grade}</td>
      <td>
        <input
          className="cell-input"
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
          onBlur={save}
          placeholder={sub.kind === "sticker" ? "Green / Gold" : "e.g. MS65"}
          maxLength={20}
          aria-label={`Expected grade for ${c.coin.inventory_number}`}
        />
      </td>
      <td className="num">
        <input
          className="cell-input num"
          value={declared}
          onChange={(e) => setDeclared(e.target.value)}
          onBlur={save}
          inputMode="decimal"
          placeholder="0.00"
          aria-label={`Declared value for ${c.coin.inventory_number}`}
        />
      </td>
      <td className="small">
        {pending ? (
          <span className="muted">Pending</span>
        ) : (
          <>
            <strong>{c.outcome_label}</strong>
            {c.after?.label && c.after.label !== c.before?.label && <div>{c.after.label}</div>}
            {c.expected_grade && c.after?.label && (
              <div className="muted">{c.after.label.includes(c.expected_grade) ? "As expected" : `Expected ${c.expected_grade}`}</div>
            )}
          </>
        )}
      </td>
      <td>
        {pending && (
          <button
            type="button"
            className="link-btn small icon-x"
            aria-label={`Take ${c.coin.inventory_number} out of this submission`}
            onClick={() => confirm(`Take ${c.coin.inventory_number} out of this submission? It goes back to In Inventory.`) && run(() => api.removeSubmissionCoin(sub.id, c.id))}
          >
            ✕
          </button>
        )}
      </td>
    </tr>
  );
}

// ---- Results --------------------------------------------------------------------------------------------------

type Row = GradingResult & { label: string; before: string };

function ResultsDialog({
  sub,
  outcomes,
  onClose,
  onSaved,
}: {
  sub: Submission;
  outcomes: Record<string, string>;
  onClose: () => void;
  onSaved: (s: Submission) => void;
}) {
  const sticker = sub.kind === "sticker";
  const choices = useMemo(
    () =>
      sticker
        ? ["sticker_green", "sticker_gold", "no_sticker"]
        : ["graded", "details", "no_grade", ...(sub.kind === "crossover" ? ["not_crossed"] : []), "returned"],
    [sticker, sub.kind],
  );
  const [rows, setRows] = useState<Row[]>(() =>
    sub.coins
      .filter((c) => c.outcome === "pending")
      .map((c) => {
        const m = /^(MS|PR|PF|SP|AU|XF|EF|VF|F|VG|G|AG|FR|PO)\s*(\d{1,2})?(\+)?/i.exec(c.expected_grade ?? "");
        return {
          link_id: c.id,
          label: `${c.coin.year}${c.coin.mint_mark !== "P" ? `-${c.coin.mint_mark}` : ""} ${c.coin.coin_type_name} (${c.coin.inventory_number})`,
          before: c.before?.label ?? c.coin.grade,
          outcome: choices[0],
          grade_prefix: m ? m[1].toUpperCase().replace("PF", "PR").replace("EF", "XF") : "MS",
          grade: m?.[2] ? Number(m[2]) : null,
          grade_plus: Boolean(m?.[3]),
          grade_star: false,
          strike_designation: null,
          cert_number: null,
          details_problem: null,
        };
      }),
  );
  const [returned, setReturned] = useState(sub.date_returned ?? todayISO());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const update = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    for (const r of rows) {
      if ((r.outcome === "graded" || r.outcome === "details") && !r.grade_prefix)
        return setError(`${r.label}: enter the grade it came back with.`);
      if (r.outcome === "graded" && !r.grade) return setError(`${r.label}: enter the grade number.`);
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await api.recordResults(sub.id, {
          date_returned: returned || null,
          results: rows.map(({ label: _l, before: _b, ...r }) => r),
        }),
      );
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="modal results-modal" role="dialog" aria-modal="true" aria-label="Record results" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h2>Record Results</h2>
        <p className="muted small">
          {sticker
            ? "Each coin's sticker result updates the coin."
            : "Each coin's new grade and cert number update the coin, and the trip is kept in its grading history."}{" "}
          The coins go back to In Inventory.
        </p>
        <label className="field w-auto">
          <span>Returned to you on</span>
          <input type="date" value={returned} max={todayISO()} onChange={(e) => setReturned(e.target.value)} />
        </label>
        <div className="result-rows">
          {rows.map((r, i) => {
            const graded = r.outcome === "graded" || r.outcome === "details";
            return (
              <fieldset key={r.link_id} className="result-row">
                <legend>
                  {r.label} <span className="muted small">· sent as {r.before}</span>
                </legend>
                <div className="row wrap">
                  <label className="field">
                    <span>Result</span>
                    <select value={r.outcome} onChange={(e) => update(i, { outcome: e.target.value })}>
                      {choices.map((o) => (
                        <option key={o} value={o}>
                          {outcomes[o] ?? o}
                        </option>
                      ))}
                    </select>
                  </label>
                  {graded && (
                    <>
                      <label className="field">
                        <span>Grade</span>
                        <div className="row tight">
                          <select value={r.grade_prefix ?? ""} onChange={(e) => update(i, { grade_prefix: e.target.value })} className="w-auto">
                            {PREFIXES.map((p) => (
                              <option key={p}>{p}</option>
                            ))}
                          </select>
                          <input
                            type="number"
                            min={1}
                            max={70}
                            value={r.grade ?? ""}
                            placeholder={r.outcome === "details" ? "optional" : "65"}
                            onChange={(e) => update(i, { grade: e.target.value ? Number(e.target.value) : null })}
                            className="grade-num"
                          />
                        </div>
                      </label>
                      {r.outcome === "graded" && (
                        <div className="field">
                          <span>&nbsp;</span>
                          <div className="checks">
                            <label>
                              <input type="checkbox" checked={Boolean(r.grade_plus)} onChange={(e) => update(i, { grade_plus: e.target.checked })} /> +
                            </label>
                            <label>
                              <input type="checkbox" checked={Boolean(r.grade_star)} onChange={(e) => update(i, { grade_star: e.target.checked })} /> ★
                            </label>
                          </div>
                        </div>
                      )}
                      {r.outcome === "graded" && (
                        <label className="field">
                          <span>Designation</span>
                          <input value={r.strike_designation ?? ""} onChange={(e) => update(i, { strike_designation: e.target.value || null })} placeholder="e.g. DMPL" maxLength={20} />
                        </label>
                      )}
                      {r.outcome === "details" && (
                        <label className="field">
                          <span>Problem</span>
                          <select value={r.details_problem ?? ""} onChange={(e) => update(i, { details_problem: e.target.value || null })}>
                            <option value="">Not stated</option>
                            {Object.entries(DETAILS_PROBLEMS).map(([k, v]) => (
                              <option key={k} value={k}>
                                {v}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                      <label className="field">
                        <span>New cert #</span>
                        <input value={r.cert_number ?? ""} onChange={(e) => update(i, { cert_number: e.target.value.trim() || null })} maxLength={30} />
                      </label>
                    </>
                  )}
                </div>
              </fieldset>
            );
          })}
        </div>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Save results"}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

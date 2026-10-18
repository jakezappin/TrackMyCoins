import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { api, type GradingCompany, type SubmissionSummary } from "../api";
import SubmissionCard from "../components/SubmissionCard";

export const COMPANIES: [GradingCompany, string][] = [
  ["NGC", "NGC"],
  ["PCGS", "PCGS"],
  ["CACG", "CAC Grading (CACG)"],
  ["CAC", "CAC sticker"],
  ["ANACS", "ANACS"],
  ["ICG", "ICG"],
];

/** Every submission to the graders: still out first, then the ones back. */
export default function GradingPage() {
  const [subs, setSubs] = useState<SubmissionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .submissions()
      .then((s) => live && setSubs(s))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, []);

  if (error) return <div className="page error">{error}</div>;
  if (!subs) return <div className="page muted">Loading…</div>;
  const out = subs.filter((s) => !s.date_returned);
  const back = subs.filter((s) => s.date_returned);

  return (
    <div className="page grading-page">
      <div className="page-head">
        <div>
          <h1>Grading Tracker</h1>
          <p className="muted small">
            Coins sent to NGC, PCGS, CAC, ANACS and ICG. The bar turns yellow at 61% of the stated turnaround, orange
            at 91% and red once it's overdue.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          + New submission
        </button>
      </div>

      {subs.length === 0 && (
        <div className="card empty-state">
          <p>
            No submissions yet. Start one here, or mark a coin <strong>At Grading</strong> on its edit page.
          </p>
        </div>
      )}
      {out.length > 0 && (
        <>
          <h2 className="section-title">Out for Grading</h2>
          <div className="submission-grid">
            {out.map((s) => (
              <SubmissionCard key={s.id} s={s} />
            ))}
          </div>
        </>
      )}
      {back.length > 0 && (
        <>
          <h2 className="section-title">Returned</h2>
          <div className="submission-grid">
            {back.map((s) => (
              <SubmissionCard key={s.id} s={s} />
            ))}
          </div>
        </>
      )}
      {creating && <NewSubmissionDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewSubmissionDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [company, setCompany] = useState<GradingCompany>("NGC");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await api.createSubmission({ company, name: name || null });
      navigate(`/grading/${s.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="modal" role="dialog" aria-modal="true" aria-label="New submission" onClick={(e) => e.stopPropagation()} onSubmit={create}>
        <h2>New Submission</h2>
        <label className="field">
          <span>Grading company</span>
          <select value={company} onChange={(e) => setCompany(e.target.value as GradingCompany)}>
            {COMPANIES.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Name (optional)</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Morgans for NGC" maxLength={100} />
        </label>
        <p className="muted small">Next you'll pick the service tier, add coins and fill in dates as it goes.</p>
        {error && <p className="error small">{error}</p>}
        <div className="row-end">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}

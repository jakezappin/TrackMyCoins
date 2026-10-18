import { Link } from "react-router-dom";
import type { GradingProgress, SubmissionSummary } from "../api";
import { shortDate } from "../format";

export const STATUS_LABEL: Record<GradingProgress["status"], string> = {
  preparing: "Preparing",
  sent: "Sent",
  at_grader: "At grader",
  shipped_back: "Shipped back",
  returned: "Returned",
};

const COLOR_WORD = { green: "On track", yellow: "Getting close", orange: "Due soon", red: "Overdue" } as const;

export function submissionTitle(s: Pick<SubmissionSummary, "number" | "name" | "company_label">) {
  return s.name ? `#${s.number} ${s.name}` : `#${s.number} ${s.company_label}`;
}

/** Days used of the stated turnaround: a bar that runs green, yellow, orange, then red once it's overdue. */
export function TurnaroundBar({ p }: { p: GradingProgress }) {
  const unit = p.business_days ? "business days" : "days";
  if (p.elapsed == null)
    return <p className="muted small turnaround-note">{p.status === "preparing" ? "Not sent yet" : "Waiting for a date"}</p>;
  const pct = p.pct ?? 0;
  return (
    <div className={`turnaround ${p.color ?? "none"}`}>
      <div
        className="turnaround-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, Math.round(pct))}
        aria-label="Turnaround used"
      >
        <div className="turnaround-fill" style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <div className="turnaround-text small">
        <strong>
          {p.elapsed}
          {p.target ? ` of ${p.target}` : ""} {unit}
        </strong>
        {p.color && <span className={`turnaround-word ${p.color}`}>{p.status === "returned" ? (pct > 100 ? "Came back late" : "Came back on time") : COLOR_WORD[p.color]}</span>}
      </div>
      <div className="muted small">
        Counting from {p.clock_from === "received" ? "when the grader received it" : "when it was sent"}
        {p.due && p.status !== "returned" ? ` · due ${shortDate(p.due)}` : ""}
      </div>
    </div>
  );
}

/** One submission at a glance (Grading Tracker page and the dashboard). */
export default function SubmissionCard({ s }: { s: SubmissionSummary }) {
  return (
    <Link to={`/grading/${s.id}`} className={`card submission-card ${s.progress.color ?? ""}`}>
      <div className="submission-card-head">
        <strong>{submissionTitle(s)}</strong>
        <span className={`status-pill ${s.progress.status}`}>{STATUS_LABEL[s.progress.status]}</span>
      </div>
      <div className="small muted">
        {s.company_label}
        {s.tier_name ? ` · ${s.tier_name}` : ""} · {s.coin_count} coin{s.coin_count === 1 ? "" : "s"}
      </div>
      <TurnaroundBar p={s.progress} />
      <div className="small muted">
        {s.date_returned
          ? `Returned ${shortDate(s.date_returned)}`
          : s.date_sent
            ? `Sent ${shortDate(s.date_sent)}`
            : `Started ${shortDate(s.created_at)}`}
      </div>
    </Link>
  );
}

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError, type RefreshJob } from "../api";

interface Props {
  /** null = every collection */
  collectionId: number | null;
  coinCount: number;
  /** Called when a refresh finishes, to reload totals. */
  onDone: () => void;
}

/** "Refresh prices" button + progress for refreshing CPG on many coins (plus PCGS data already fetched this week) at once. */
export default function RefreshPrices({ collectionId, coinCount, onDone }: Props) {
  const [asking, setAsking] = useState(false);
  const [job, setJob] = useState<RefreshJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);
  const timer = useRef<number | null>(null);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const [allow, setAllow] = useState<{ limit: number; left: number; next_available_at: string | null } | null>(null);
  const loadAllowance = () => api.refreshAllowance().then(setAllow).catch(() => undefined);
  useEffect(() => {
    loadAllowance();
  }, []);
  useEffect(() => setSlot(document.getElementById("refresh-slot")), []);

  // Pick up a refresh that's already running (e.g. after leaving and coming back).
  useEffect(() => {
    api.currentJob().then((j) => j && setJob(j)).catch(() => undefined);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  // Poll while it runs. A failed check retries (backing off); a job the server no longer knows (it restarted)
  // ends the wait instead of leaving the button stuck on "Refreshing…".
  const misses = useRef(0);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const delay = Math.min(1000 * 2 ** misses.current, 15000);
    timer.current = window.setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        misses.current = 0;
        setError(null);
        setJob(j);
        if (j.status !== "running") onDone();
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          setJob({ ...job, status: "failed", messages: [...job.messages, "The server restarted; this refresh stopped."] });
          onDone();
          return;
        }
        misses.current += 1;
        setError(`${(e as Error).message} Still trying…`);
        setTick((t) => t + 1); // poll again
      }
    }, delay);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [job, onDone, tick]);

  async function start() {
    setAsking(false);
    setError(null);
    setShowLog(false);
    try {
      setJob(await api.refreshPrices(collectionId, true));
      loadAllowance();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const running = job?.status === "running";
  const pct = job && job.total ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <>
      <button
        className="btn"
        onClick={() => setAsking(true)}
        disabled={running || coinCount === 0 || allow?.left === 0}
        title={allow?.left === 0 ? `Next refresh available ${nextLabel(allow.next_available_at)}` : undefined}
      >
        {running ? `Refreshing… ${pct}%` : allow?.left === 0 ? `Refresh prices · ${nextLabel(allow.next_available_at, true)}` : "Refresh prices"}
      </button>

      {asking && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={() => setAsking(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <h2>Refresh Prices</h2>
            <p className="muted">
              Gets the latest CPG value for {collectionId == null ? "every coin you own" : "every coin in this collection"}{" "}
              ({coinCount} coin{coinCount === 1 ? "" : "s"}). Sold coins and coins without a numeric grade are skipped.
            </p>
            <p className="small muted">
              PCGS Price Guide and auction data already fetched this week are included. To fetch new PCGS data, use Get
              PCGS Data on a coin's page (PCGS allows only 100 lookups a day for the whole site).
            </p>
            {allow && (
              <p className="small muted">
                You can refresh prices {allow.limit} times a week to keep within our price providers' limits.{" "}
                <strong>
                  {allow.left} of {allow.limit} left
                </strong>{" "}
                this week. Single coins can still be priced from their own page any time.
              </p>
            )}
            <div className="row-end">
              <button className="btn" onClick={() => setAsking(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={start}>
                Start
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <p className="error small">{error}</p>}

      {job && slot && createPortal(
        <div className="card refresh-panel">
          <div className="refresh-head">
            <strong>
              {running ? "Refreshing prices" : job.status === "failed" ? "Refresh stopped" : "Prices refreshed"} ·{" "}
              {job.scope}
            </strong>
            {!running && (
              <button className="link-btn small" onClick={() => setJob(null)}>
                Dismiss
              </button>
            )}
          </div>
          <div className="progress">
            <div className="progress-bar" style={{ width: `${pct}%` }} />
          </div>
          <div className="small muted refresh-stats">
            <span>
              {job.done} of {job.total}
            </span>
            <span className="pos">{job.updated} updated</span>
            {job.skipped > 0 && <span>{job.skipped} skipped</span>}
            {job.failed > 0 && <span className="neg">{job.failed} couldn't be priced</span>}
            {running && job.current && <span className="truncate">Now: {job.current}</span>}
          </div>
          {job.pcgs_stopped && <p className="small warn">PCGS stopped: {job.pcgs_stopped}</p>}
          {job.messages.length > 0 && (
            <>
              <button className="link-btn small" onClick={() => setShowLog((v) => !v)}>
                {showLog ? "Hide details" : `Show details (${job.messages.length})`}
              </button>
              {showLog && (
                <ul className="refresh-log small">
                  {job.messages.map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>,
        slot,
      )}
    </>
  );
}

/** Where the progress panel appears (full width, under the page header). */
export function RefreshSlot() {
  return <div id="refresh-slot" />;
}

/** "Tue Oct 21, 3:40 PM", or "Tue" for the button. */
function nextLabel(iso: string | null, short = false): string {
  if (!iso) return "";
  const d = new Date(iso);
  return short
    ? `next ${d.toLocaleDateString(undefined, { weekday: "short" })}`
    : d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type RefreshJob } from "../api";

interface Props {
  /** null = every collection */
  collectionId: number | null;
  coinCount: number;
  /** Called when a refresh finishes, to reload totals. */
  onDone: () => void;
}

/** "Refresh prices" button + progress for refreshing CPG (and optionally PCGS) on many coins at once. */
export default function RefreshPrices({ collectionId, coinCount, onDone }: Props) {
  const [asking, setAsking] = useState(false);
  const [includePcgs, setIncludePcgs] = useState(false);
  const [job, setJob] = useState<RefreshJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);
  const timer = useRef<number | null>(null);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => setSlot(document.getElementById("refresh-slot")), []);

  // Pick up a refresh that's already running (e.g. after leaving and coming back).
  useEffect(() => {
    api.currentJob().then((j) => j && setJob(j)).catch(() => undefined);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, []);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    timer.current = window.setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if (j.status !== "running") onDone();
      } catch (e) {
        setError((e as Error).message);
      }
    }, 1000);
  }, [job, onDone]);

  async function start() {
    setAsking(false);
    setError(null);
    setShowLog(false);
    try {
      setJob(await api.refreshPrices(collectionId, includePcgs));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const running = job?.status === "running";
  const pct = job && job.total ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <>
      <button className="btn" onClick={() => setAsking(true)} disabled={running || coinCount === 0}>
        {running ? `Refreshing… ${pct}%` : "Refresh prices"}
      </button>

      {asking && (
        <div className="modal-backdrop" onClick={() => setAsking(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Refresh prices</h2>
            <p className="muted">
              Gets the latest CPG value for {collectionId == null ? "every coin you own" : "every coin in this collection"}{" "}
              ({coinCount} coin{coinCount === 1 ? "" : "s"}). Sold coins and coins without a numeric grade are skipped.
            </p>
            <label className="checks">
              <span>
                <input type="checkbox" checked={includePcgs} onChange={(e) => setIncludePcgs(e.target.checked)} /> Also
                get PCGS Price Guide, population and auction sales
              </span>
            </label>
            {includePcgs && (
              <p className="small warn">
                Uses 2 of PCGS's 1,000 free API calls per day for each coin ({coinCount * 2} calls). If the limit is
                reached, PCGS stops for the day and CPG keeps going.
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

import { useRef, useState } from "react";
import { api, saveFile, type CleanupResult } from "../api";

/** Spreadsheet cleanup: match a messy file's columns, standardize every row, show what changed and what still needs
 * fixing, then download the cleaned file or import it straight away. */
export default function CleanupTool({ onImport }: { onImport: (cleaned: File) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<CleanupResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [show, setShow] = useState<"problems" | "changed" | "all">("problems");

  async function run(f: File, m: Record<string, string>) {
    setBusy("Cleaning…");
    setError(null);
    try {
      setResult(await api.cleanup(f, m));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function cleaned(then: (f: File) => void, label: string) {
    if (!file) return;
    setBusy(label);
    setError(null);
    try {
      then(await api.cleanupFile(file, mapping));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const rows = result
    ? result.rows.filter((r) => (show === "problems" ? r.problems.length : show === "changed" ? r.changes.length : true))
    : [];

  return (
    <div className="stack cleanup">
      <p className="muted small">
        Got a spreadsheet in your own format? Clean it up first: TrackMyCoins matches your columns, splits run-together
        descriptions (like <em>1881-S Morgan PCGS MS65 CAC 12345678</em>), standardizes dates, grades, services and
        prices, and lists what changed and anything it couldn't work out. Then download the cleaned file or import it.
      </p>
      <div className="row">
        <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => input.current?.click()}>
          {busy === "Cleaning…" && !result ? busy : file ? "Choose another file" : "Choose file"}
        </button>
        {file && <span className="small muted">{file.name}</span>}
        <input
          ref={input}
          type="file"
          hidden
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (!f) return;
            setFile(f);
            setMapping({});
            setResult(null);
            run(f, {});
          }}
        />
      </div>
      {error && <p className="error small">{error}</p>}

      {result && file && (
        <>
          <h3 className="details-sub">Your Columns</h3>
          <p className="muted small">Each of your columns and what it's read as. Change any that are wrong, or keep a column's text in Notes.</p>
          <div className="table-scroll">
            <table className="history cleanup-columns">
              <thead>
                <tr>
                  <th>Your column</th>
                  <th>Examples</th>
                  <th>Read as</th>
                </tr>
              </thead>
              <tbody>
                {result.headers.map((h) => (
                  <tr key={h.header}>
                    <td>
                      <strong>{h.header}</strong>
                    </td>
                    <td className="small muted">{h.samples.join(" · ") || "(empty)"}</td>
                    <td>
                      <select
                        value={h.field}
                        disabled={busy !== null}
                        onChange={(e) => {
                          const next = { ...mapping, [h.header]: e.target.value };
                          setMapping(next);
                          run(file, next);
                        }}
                        aria-label={`What ${h.header} is`}
                        className={h.field ? "" : "unmapped"}
                      >
                        {result.choices.map((c) => (
                          <option key={c.field || "ignore"} value={c.field}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="cards cleanup-counts">
            <div className="card stat">
              <div className="stat-label">Rows</div>
              <div className="stat-value">{result.counts.rows}</div>
            </div>
            <div className="card stat">
              <div className="stat-label">Cleaned up</div>
              <div className="stat-value">{result.counts.changed}</div>
              <div className="stat-note">rows with something standardized</div>
            </div>
            <div className="card stat">
              <div className="stat-label">Need fixing</div>
              <div className={`stat-value ${result.counts.problems ? "neg" : ""}`}>{result.counts.problems}</div>
              <div className="stat-note">{result.counts.problems ? "fix in your file, or import the rest" : "all rows ready"}</div>
            </div>
          </div>

          <div className="row wrap between">
            <div className="segmented small-seg" role="radiogroup" aria-label="Rows to show">
              {(
                [
                  ["problems", `Need fixing (${result.counts.problems})`],
                  ["changed", `Changed (${result.counts.changed})`],
                  ["all", `All (${result.counts.rows})`],
                ] as const
              ).map(([k, label]) => (
                <button key={k} type="button" role="radio" aria-checked={show === k} className={`seg ${show === k ? "active" : ""}`} onClick={() => setShow(k)}>
                  {label}
                </button>
              ))}
            </div>
            <div className="row">
              <button type="button" className="btn" disabled={busy !== null} onClick={() => cleaned(saveFile, "Preparing…")}>
                {busy === "Preparing…" ? busy : "Download cleaned file"}
              </button>
              <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => cleaned(onImport, "Importing…")}>
                {busy === "Importing…" ? "Opening…" : "Import cleaned rows"}
              </button>
            </div>
          </div>

          {rows.length === 0 ? (
            <p className="muted small">{show === "problems" ? "Nothing needs fixing." : "Nothing to show."}</p>
          ) : (
            <ul className="import-list cleanup-rows">
              {rows.map((r) => (
                <li key={`${r.sheet}-${r.row}`} className={`import-row ${r.problems.length ? "bad" : ""}`}>
                  <div className="import-main">
                    <strong>
                      {[r.cleaned.Date, r.cleaned.Type, r.cleaned.Grade, r.cleaned["Grading service"] !== "Raw" ? r.cleaned["Grading service"] : "Raw", r.cleaned["Cert #"] && `#${r.cleaned["Cert #"]}`]
                        .filter(Boolean)
                        .join(" ")}
                    </strong>
                    <span className="small muted">row {r.row}</span>
                    {r.changes.map((c) => (
                      <span key={c.column} className="small cleanup-change">
                        <span className="muted">{c.column}:</span> {c.before ? <del>{c.before}</del> : <em className="muted">empty</em>} → {c.after || <em className="muted">empty</em>}
                      </span>
                    ))}
                    {r.problems.map((p) => (
                      <span key={p} className="small error">
                        {p}
                      </span>
                    ))}
                    {(r.notes ?? []).map((n) => (
                      <span key={n} className="small warn">
                        {n}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

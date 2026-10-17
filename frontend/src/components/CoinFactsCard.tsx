import type { CoinFacts } from "../api";
import { shortDate } from "../format";

const n = (v: number) => v.toLocaleString();

/** Mintage, specifications and PCGS population, from data PCGS already gave us (no extra API calls). */
export default function CoinFactsCard({
  facts,
  canFetch,
  busy,
  onFetch,
}: {
  facts: CoinFacts | null;
  canFetch: boolean;
  busy: boolean;
  onFetch: () => void;
}) {
  if (!facts) {
    return (
      <section className="card coin-facts">
        <h2>Coin facts</h2>
        <p className="muted small">
          Mintage, specifications and PCGS population appear here after a PCGS cert lookup or when PCGS data is fetched
          for this coin.
        </p>
        {canFetch && (
          <div>
            <button type="button" className="btn" onClick={onFetch} disabled={busy}>
              {busy ? "Fetching…" : "Get PCGS Data"}
            </button>
          </div>
        )}
      </section>
    );
  }
  const specs: [string, string | null][] = [
    ["Mintage", facts.mintage ? n(facts.mintage) : null],
    ["Mint", facts.mint_location],
    ["Composition", facts.metal],
    ["Weight", facts.weight_g ? `${facts.weight_g} g` : null],
    ["Diameter", facts.diameter_mm ? `${facts.diameter_mm} mm` : null],
    ["Edge", facts.edge],
    ["Designer", facts.designer],
  ];
  const shown = specs.filter(([, v]) => v);
  const hasPop = facts.population != null;
  return (
    <section className="card coin-facts">
      <h2>Coin facts</h2>
      {hasPop && (
        <dl className="market-stats">
          <div>
            <dt>PCGS pop{facts.pop_grade ? ` in ${facts.pop_grade}` : ""}</dt>
            <dd>{n(facts.population!)}</dd>
          </div>
          {facts.pop_higher != null && (
            <div>
              <dt>Graded higher</dt>
              <dd>{n(facts.pop_higher)}</dd>
            </div>
          )}
          {facts.mintage ? (
            <div>
              <dt>Mintage</dt>
              <dd>{n(facts.mintage)}</dd>
            </div>
          ) : null}
        </dl>
      )}
      {shown.length > 0 && (
        <dl className="facts">
          {shown
            .filter(([k]) => !(hasPop && k === "Mintage"))
            .map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
        </dl>
      )}
      <p className="muted small">
        From PCGS{facts.pcgs_number ? ` #${facts.pcgs_number}` : ""}
        {facts.as_of ? `, ${facts.source === "cert_lookup" ? "at cert lookup" : "as of"} ${shortDate(facts.as_of)}` : ""}.
        {hasPop ? " Population counts PCGS-graded coins only." : ""}
      </p>
    </section>
  );
}

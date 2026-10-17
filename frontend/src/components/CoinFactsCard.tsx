import type { CoinFacts } from "../api";
import { money, shortDate } from "../format";
import CollapseHead from "./CollapseHead";
import useCollapsed from "./useCollapsed";

const n = (v: number) => v.toLocaleString();
const compactN = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(v >= 1e7 ? 1 : 2)}M` : n(v));

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
  const [collapsed, toggle] = useCollapsed("coin-facts-collapsed");
  if (!facts) {
    return (
      <section className={`card coin-facts${collapsed ? " collapsed" : ""}`}>
        <CollapseHead title="Coin Facts" collapsed={collapsed} onToggle={toggle} />
        {!collapsed && (
        <>
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
        </>
        )}
      </section>
    );
  }
  const melt = facts.melt;
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
  if (collapsed) {
    const bits = [
      hasPop ? `PCGS pop ${n(facts.population!)}${facts.pop_grade ? ` in ${facts.pop_grade}` : ""}` : null,
      facts.mintage ? `mintage ${compactN(facts.mintage)}` : null,
      melt ? `melt ${money(melt.value)}` : null,
    ].filter(Boolean);
    return (
      <section className="card coin-facts collapsed">
        <CollapseHead title="Coin Facts" collapsed onToggle={toggle} />
        {bits.length > 0 && <p className="muted small collapsed-summary">{bits.join(" · ")}</p>}
      </section>
    );
  }
  return (
    <section className="card coin-facts">
      <CollapseHead title="Coin Facts" collapsed={false} onToggle={toggle} />
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
      {melt && (
        <dl className="market-stats">
          <div>
            <dt>Melt value</dt>
            <dd>{money(melt.value)}</dd>
          </div>
          <div className="melt-detail">
            <dt>Metal content</dt>
            <dd className="small">
              {melt.metals.map((m) => `${m.oz.toFixed(4)} oz ${m.metal} × ${money(m.spot)}`).join(" + ")}
            </dd>
          </div>
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
        {melt ? ` Melt uses live spot prices${melt.as_of ? ` (${new Date(melt.as_of).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })})` : ""}.` : ""}
      </p>
    </section>
  );
}

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Collection, type Upgrades } from "../api";
import { coinPath, collectionPath, gradeLabel, money } from "../format";
import AddWant from "../components/AddWant";

/** For each date in a set: the best coin owned, the next grade up, and what upgrading would cost. */
export default function UpgradesPage() {
  const { typeSlug = "", number } = useParams();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [data, setData] = useState<Upgrades | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api
      .collectionByNumber(typeSlug, Number(number))
      .then(async (c) => {
        setCollection(c);
        setData(await api.upgrades(c.id));
      })
      .catch((e) => setError((e as Error).message));
  }, [typeSlug, number]);

  if (error) return <div className="page error">{error}</div>;
  if (!collection || !data) return <div className="page muted">Loading…</div>;

  return (
    <div className="page upgrades-page">
      <div className="row">
        <Link className="btn back-btn" to={collectionPath(collection)}>
          ← Back to {collection.name}
        </Link>
      </div>
      <div className="page-head">
        <div>
          <h1>Upgrade Finder</h1>
          <p className="muted">
            {collection.name} · the next grade up for each coin and what it would cost, cheapest first
          </p>
        </div>
      </div>

      <section className="card table-card">
        {data.items.length === 0 ? (
          <p className="muted empty">
            {data.unpriced.length ? "No priced coins yet. Use Refresh prices to get CPG for every grade." : "Nothing to upgrade."}
          </p>
        ) : (
          <div className="table-scroll">
            <table className="upgrade-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Your best</th>
                  <th className="num">Value now</th>
                  <th>Next grade</th>
                  <th className="num">CPG</th>
                  <th className="num">Cost to upgrade</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.label}>
                    <td className="strong c-label">{u.label}</td>
                    <td className="c-coin">
                      <Link to={coinPath(u.coin.inventory_number)}>
                        {gradeLabel({ ...u.coin, grading_service: "PCGS" })}
                        {u.coin.cac ? " CAC" : ""}
                      </Link>
                    </td>
                    <td className="num c-now" data-label="Now">{money(u.current_value)}</td>
                    <td className="c-next" data-label="Next">{u.next_label}</td>
                    <td className="num c-cpg" data-label="CPG">{money(u.next_cpg)}</td>
                    <td className="num strong c-cost" data-label="Upgrade">
                      {u.cost != null ? (Number(u.cost) >= 0 ? `+${money(u.cost)}` : money(u.cost)) : "—"}
                      {u.pct != null && <span className="small muted"> ({u.pct >= 0 ? "+" : ""}{u.pct}%)</span>}
                    </td>
                    <td className="c-want">
                      <AddWant
                        collectionId={collection.id}
                        year={u.year}
                        mintMark={u.mint_mark}
                        variety={u.variety}
                        grade={u.next_grade}
                        gradePrefix={u.coin.grade_prefix}
                        maxPrice={u.next_cpg}
                        label={`${u.label} ${u.next_label}`}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {data.unpriced.length > 0 && (
        <p className="muted small">
          Not included until priced ({data.unpriced.length}): {data.unpriced.join(", ")}. Refresh prices to add them.
        </p>
      )}
      {data.at_top.length > 0 && (
        <p className="muted small">Already at the top priced grade: {data.at_top.join(", ")}.</p>
      )}
    </div>
  );
}

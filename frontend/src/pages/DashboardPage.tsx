import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../App";
import NewCollectionDialog from "../components/NewCollectionDialog";
import { collectionPath, collectionsBySeries, FINISH_LABEL, money, soldPath } from "../format";

export default function DashboardPage() {
  const { user, coinTypes, collections } = useApp();
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const groups = collectionsBySeries(coinTypes, collections);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Welcome, {user?.first_name}</h1>
          <p className="muted">Pick a collection, or start a new one.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          + New collection
        </button>
      </div>

      {groups.length === 0 && (
        <div className="card empty-state">
          <p>You don't have any collections yet.</p>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            Create your first collection
          </button>
        </div>
      )}

      {groups.map(({ type, collections: cols }) => (
        <section key={type.id} className="section">
          <div className="section-head">
            <h2>{type.plural}</h2>
            <Link className="btn" to={soldPath(type.slug)}>
              View sold
            </Link>
          </div>
          <div className="collection-grid">
            {cols.map((c) => (
              <Link key={c.id} to={collectionPath(c)} className="card collection-tile">
                <h3>
                  {c.name}
                  {c.finish !== "MS" && <span className="tag finish">{FINISH_LABEL[c.finish]}</span>}
                </h3>
                <div className="muted small">
                  {c.summary.coin_count} coin{c.summary.coin_count === 1 ? "" : "s"}
                </div>
                <dl className="mini-stats">
                  <div>
                    <dt>Paid</dt>
                    <dd>{money(c.summary.total_price_paid)}</dd>
                  </div>
                  <div>
                    <dt>CPG</dt>
                    <dd>{money(c.summary.total_cpg_value)}</dd>
                  </div>
                  <div>
                    <dt>Wholesale</dt>
                    <dd>{money(c.summary.est_wholesale_value)}</dd>
                  </div>
                </dl>
              </Link>
            ))}
          </div>
        </section>
      ))}

      {creating && (
        <NewCollectionDialog onClose={() => setCreating(false)} onCreated={(c) => navigate(collectionPath(c))} />
      )}
    </div>
  );
}

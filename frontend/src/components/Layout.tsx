import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";
import { collectionPath, collectionsBySeries, FINISH_LABEL, soldPath } from "../format";
import NewCollectionDialog from "./NewCollectionDialog";

export default function Layout() {
  const { user, setUser, coinTypes, collections } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const loc = useLocation();
  const navigate = useNavigate();

  useEffect(() => setMenuOpen(false), [loc.pathname]);

  async function logout() {
    await api.logout();
    setUser(null);
    navigate("/login");
  }

  // If we're on a collection page, "Add coin" pre-selects that collection.
  const m = loc.pathname.match(/^\/collections\/([^/]+)\/(\d+)/);
  const current = m && collections.find((c) => c.collection_type_slug === m[1] && c.number === Number(m[2]));
  const addCoinHref = current ? `/coins/new?collection=${current.id}` : "/coins/new";

  return (
    <div className="shell">
      <header className="topbar">
        <button className="icon-btn" aria-label="Menu" onClick={() => setMenuOpen((o) => !o)}>
          ☰
        </button>
        <Link to="/" className="brand">
          <span className="brand-mark">◉</span> Coin Collection
        </Link>
      </header>

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <Link to="/" className="brand desktop-only">
          <span className="brand-mark">◉</span> Coin Collection
        </Link>

        <nav>
          <NavLink to="/" end className="nav-item">
            Dashboard
          </NavLink>

          <button className="nav-item nav-action" onClick={() => setCreating(true)}>
            + New collection
          </button>

          {collectionsBySeries(coinTypes, collections).map(({ type, collections: cols }) => (
            <div key={type.id} className="nav-group">
              <div className="nav-heading">{type.plural}</div>
              {cols.map((c) => (
                <NavLink key={c.id} to={collectionPath(c)} className="nav-item">
                  <span className="truncate">
                    {c.name}
                    {c.finish !== "MS" && <span className="finish-tag">{FINISH_LABEL[c.finish]}</span>}
                  </span>
                  <span className="count">{c.summary.coin_count}</span>
                </NavLink>
              ))}
              <NavLink to={soldPath(type.slug)} className="nav-item nav-sold">
                Sold
              </NavLink>
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <Link to={addCoinHref} className="btn btn-primary btn-block">
            + Add coin
          </Link>
          <NavLink to="/account" className="nav-item account-link">
            <span className="avatar" aria-hidden>
              {(user?.first_name?.[0] ?? "") + (user?.last_name?.[0] ?? "")}
            </span>
            <span className="truncate">
              {user?.first_name} {user?.last_name}
              <span className="account-sub">Account settings</span>
            </span>
          </NavLink>
          <button className="link-btn logout" onClick={logout}>
            Log out
          </button>
        </div>
      </aside>
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}

      <main className="content">
        <Outlet />
      </main>

      {creating && (
        <NewCollectionDialog
          onClose={() => setCreating(false)}
          onCreated={(c) => {
            setCreating(false);
            navigate(collectionPath(c));
          }}
        />
      )}
    </div>
  );
}

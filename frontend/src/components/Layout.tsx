import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";
import { collectionPath, collectionsBySeries, FINISH_LABEL, soldPath } from "../format";
import Logo from "./Logo";
import NewBullionDialog from "./NewBullionDialog";
import NewCollectionDialog from "./NewCollectionDialog";

export default function Layout() {
  const { user, setUser, coinTypes, collections, bullionCollections, navCollection } = useApp();
  // Item pages and forms aren't under their collection's address: highlight it anyway.
  const navClass = (kind: "coin" | "bullion", id: number) => ({ isActive }: { isActive: boolean }) =>
    `nav-item${isActive || (navCollection?.kind === kind && navCollection.id === id) ? " active" : ""}`;
  const [menuOpen, setMenuOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [creatingBullion, setCreatingBullion] = useState(false);
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
        <Link to="/dashboard" className="brand">
          <Logo size={26} tone="light" />
        </Link>
      </header>

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <Link to="/dashboard" className="brand desktop-only">
          <Logo size={28} tone="light" />
        </Link>

        <nav>
          <NavLink to="/dashboard" end className="nav-item">
            Dashboard
          </NavLink>
          <NavLink to="/wants" className="nav-item">
            Want List
          </NavLink>
          <NavLink to="/metals" className="nav-item">
            Precious Metals
          </NavLink>

          <button className="nav-item nav-action" onClick={() => setCreating(true)}>
            + New collection
          </button>

          {collectionsBySeries(coinTypes, collections).map(({ type, collections: cols }) => (
            <div key={type.id} className="nav-group">
              <div className="nav-heading">{type.plural}</div>
              {cols.map((c) => (
                <NavLink key={c.id} to={collectionPath(c)} className={navClass("coin", c.id)}>
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

          <div className="nav-group">
            <div className="nav-heading">Bullion</div>
            {bullionCollections.map((c) => (
              <NavLink key={c.id} to={`/bullion/${c.id}`} className={navClass("bullion", c.id)}>
                <span className="truncate">{c.name}</span>
                <span className="count">{c.summary.count}</span>
              </NavLink>
            ))}
            <button className="nav-item nav-action" onClick={() => setCreatingBullion(true)}>
              + New bullion collection
            </button>
          </div>
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

      {creatingBullion && <NewBullionDialog onClose={() => setCreatingBullion(false)} />}
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

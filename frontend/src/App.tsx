import { createContext, Fragment, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError, setUnauthorizedHandler, type BullionCollection, type CoinType, type Collection, type User } from "./api";
import Layout from "./components/Layout";
import CoinDetailPage from "./pages/CoinDetailPage";
import CoinFormPage from "./pages/CoinFormPage";
import CollectionPage from "./pages/CollectionPage";
import AccountPage from "./pages/AccountPage";
import DashboardPage from "./pages/DashboardPage";
import ImportPage from "./pages/ImportPage";
import NgcButtonPage from "./pages/NgcButtonPage";
import { NGC_BOOKMARK_ENABLED } from "./ngcButton";
import UpgradesPage from "./pages/UpgradesPage";
import MetalsPage from "./pages/MetalsPage";
import GradingPage from "./pages/GradingPage";
import StoragePage from "./pages/StoragePage";
import StorageSpotPage from "./pages/StorageSpotPage";
import SubmissionPage from "./pages/SubmissionPage";
import WantListPage from "./pages/WantListPage";
import LandingPage from "./pages/LandingPage";
import { LoginPage, SignupPage } from "./pages/AuthPages";
import SharedCollectionPage from "./pages/SharedCollectionPage";
import PublicCoinPage from "./pages/PublicCoinPage";
import LabelsPage from "./pages/LabelsPage";
import DealersPage from "./pages/DealersPage";
import DealerPage from "./pages/DealerPage";
import SoldPage from "./pages/SoldPage";
import StatusPage from "./pages/StatusPage";
import BullionCollectionPage from "./pages/BullionCollectionPage";
import BullionFormPage from "./pages/BullionFormPage";
import BullionItemPage from "./pages/BullionItemPage";

interface AppState {
  user: User | null;
  setUser: (u: User | null) => void;
  coinTypes: CoinType[];
  collections: Collection[];
  bullionCollections: BullionCollection[];
  /** The collection the current page belongs to (an item or its form), so the sidebar keeps it highlighted. */
  navCollection: NavCollection | null;
  setNavCollection: (c: NavCollection | null) => void;
  /** Re-fetch collections (and their totals) after anything changes. */
  refresh: () => Promise<void>;
  /** Collections have been fetched at least once (until then, empty lists mean "not loaded yet"). */
  loaded: boolean;
  /** Why the collections couldn't be loaded, if they couldn't. */
  loadError: string | null;
}

export type NavCollection = { kind: "coin" | "bullion"; id: number };

const AppContext = createContext<AppState | null>(null);

/** Pages for one item (or its form) call this so the sidebar keeps its collection highlighted. */
export function useNavCollection(kind: NavCollection["kind"], id: number | null | undefined) {
  const { setNavCollection } = useApp();
  useEffect(() => {
    setNavCollection(id ? { kind, id } : null);
    return () => setNavCollection(null);
  }, [kind, id, setNavCollection]);
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}

/** A page starts fresh at each address: nothing (form fields, errors, a slow earlier request) carries over from
 * the coin, collection or series shown before, as it would if React reused the page between addresses. */
function Fresh({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  return <Fragment key={loc.pathname + loc.search}>{children}</Fragment>;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [coinTypes, setCoinTypes] = useState<CoinType[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [bullionCollections, setBullionCollections] = useState<BullionCollection[]>([]);
  const [navCollection, setNavCollection] = useState<NavCollection | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Escape closes the dialog on top, the same as clicking outside it (which a dialog ignores while it's saving).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      const backdrops = document.querySelectorAll<HTMLElement>(".modal-backdrop");
      backdrops[backdrops.length - 1]?.click();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Dialogs take keyboard focus when they open (first field or button, unless one asked for it) and hand it back
  // to where it was when they close.
  useEffect(() => {
    const returnTo = new Map<Element, HTMLElement | null>();
    const focusables = 'input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled), button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])';
    const obs = new MutationObserver(() => {
      document.querySelectorAll<HTMLElement>(".modal").forEach((m) => {
        if (returnTo.has(m)) return;
        returnTo.set(m, document.activeElement as HTMLElement | null);
        if (!m.contains(document.activeElement)) m.querySelector<HTMLElement>(focusables)?.focus();
      });
      for (const [m, prev] of returnTo) {
        if (!document.body.contains(m)) {
          returnTo.delete(m);
          if (prev && document.body.contains(prev)) prev.focus();
        }
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    return () => obs.disconnect();
  }, []);

  // Session ran out: back to the login page (which returns here after signing in).
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) console.error(e);
      })
      .finally(() => setChecking(false));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [types, cols, bullion] = await Promise.all([api.coinTypes(), api.collections(), api.bullionCollections()]);
      setCoinTypes(types);
      setCollections(cols);
      setBullionCollections(bullion);
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (user) refresh();
    else {
      setCoinTypes([]);
      setCollections([]);
      setBullionCollections([]);
      setLoaded(false);
    }
  }, [user, refresh]);

  if (checking) return <div className="center-screen muted">Loading…</div>;

  return (
    <AppContext.Provider value={{ user, setUser, coinTypes, collections, bullionCollections, navCollection, setNavCollection, refresh, loaded, loadError }}>
      <Routes>
        <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <LandingPage />} />
        <Route path="/login" element={user ? <Navigate to="/dashboard" /> : <LoginPage />} />
        <Route path="/signup" element={user ? <Navigate to="/dashboard" /> : <SignupPage />} />
        <Route path="/shared/:token" element={<SharedCollectionPage />} />
        <Route path="/c/:token" element={<Fresh><PublicCoinPage /></Fresh>} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/wants" element={<WantListPage />} />
          <Route path="/metals" element={<MetalsPage />} />
          <Route path="/grading" element={<GradingPage />} />
          <Route path="/grading/:id" element={<Fresh><SubmissionPage /></Fresh>} />
          <Route path="/storage" element={<StoragePage />} />
          <Route path="/storage/:id" element={<Fresh><StorageSpotPage /></Fresh>} />
          <Route path="/labels" element={<Fresh><LabelsPage /></Fresh>} />
          <Route path="/dealers" element={<DealersPage />} />
          <Route path="/dealers/:id" element={<Fresh><DealerPage /></Fresh>} />
          <Route path="/collections/:typeSlug/:number/upgrades" element={<Fresh><UpgradesPage /></Fresh>} />
          {NGC_BOOKMARK_ENABLED && <Route path="/ngc-button" element={<NgcButtonPage />} />}
          <Route path="/collections/:typeSlug/sold" element={<Fresh><SoldPage /></Fresh>} />
          <Route path="/collections/:typeSlug/:number" element={<Fresh><CollectionPage /></Fresh>} />
          <Route path="/collections/:typeSlug/:number/status" element={<Fresh><StatusPage /></Fresh>} />
          <Route path="/coins/new" element={<Fresh><CoinFormPage /></Fresh>} />
          <Route path="/coins/:inv" element={<Fresh><CoinDetailPage /></Fresh>} />
          <Route path="/coins/:inv/edit" element={<Fresh><CoinFormPage /></Fresh>} />
          <Route path="/bullion/:id" element={<Fresh><BullionCollectionPage /></Fresh>} />
          <Route path="/bullion/items/new" element={<Fresh><BullionFormPage /></Fresh>} />
          <Route path="/bullion/items/:inv" element={<Fresh><BullionItemPage /></Fresh>} />
          <Route path="/bullion/items/:inv/edit" element={<Fresh><BullionFormPage /></Fresh>} />
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </AppContext.Provider>
  );
}

function RequireAuth() {
  const { user } = useApp();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname + loc.search + loc.hash }} replace />;
  return <Layout />;
}

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError, type BullionCollection, type CoinType, type Collection, type User } from "./api";
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
import WantListPage from "./pages/WantListPage";
import LandingPage from "./pages/LandingPage";
import { LoginPage, SignupPage } from "./pages/AuthPages";
import SharedCollectionPage from "./pages/SharedCollectionPage";
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
  /** Re-fetch collections (and their totals) after anything changes. */
  refresh: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [coinTypes, setCoinTypes] = useState<CoinType[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [bullionCollections, setBullionCollections] = useState<BullionCollection[]>([]);

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
    const [types, cols, bullion] = await Promise.all([api.coinTypes(), api.collections(), api.bullionCollections()]);
    setCoinTypes(types);
    setCollections(cols);
    setBullionCollections(bullion);
  }, []);

  useEffect(() => {
    if (user) refresh();
    else {
      setCoinTypes([]);
      setCollections([]);
      setBullionCollections([]);
    }
  }, [user, refresh]);

  if (checking) return <div className="center-screen muted">Loading…</div>;

  return (
    <AppContext.Provider value={{ user, setUser, coinTypes, collections, bullionCollections, refresh }}>
      <Routes>
        <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <LandingPage />} />
        <Route path="/login" element={user ? <Navigate to="/dashboard" /> : <LoginPage />} />
        <Route path="/signup" element={user ? <Navigate to="/dashboard" /> : <SignupPage />} />
        <Route path="/shared/:token" element={<SharedCollectionPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/wants" element={<WantListPage />} />
          <Route path="/collections/:typeSlug/:number/upgrades" element={<UpgradesPage />} />
          {NGC_BOOKMARK_ENABLED && <Route path="/ngc-button" element={<NgcButtonPage />} />}
          <Route path="/collections/:typeSlug/sold" element={<SoldPage />} />
          <Route path="/collections/:typeSlug/:number" element={<CollectionPage />} />
          <Route path="/collections/:typeSlug/:number/status" element={<StatusPage />} />
          <Route path="/coins/new" element={<CoinFormPage />} />
          <Route path="/coins/:inv" element={<CoinDetailPage />} />
          <Route path="/coins/:inv/edit" element={<CoinFormPage />} />
          <Route path="/bullion/:id" element={<BullionCollectionPage />} />
          <Route path="/bullion/items/new" element={<BullionFormPage />} />
          <Route path="/bullion/items/:inv" element={<BullionItemPage />} />
          <Route path="/bullion/items/:inv/edit" element={<BullionFormPage />} />
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

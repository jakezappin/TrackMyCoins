import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError, type CoinType, type Collection, type User } from "./api";
import Layout from "./components/Layout";
import CoinDetailPage from "./pages/CoinDetailPage";
import CoinFormPage from "./pages/CoinFormPage";
import CollectionPage from "./pages/CollectionPage";
import AccountPage from "./pages/AccountPage";
import DashboardPage from "./pages/DashboardPage";
import LandingPage from "./pages/LandingPage";
import { LoginPage, SignupPage } from "./pages/AuthPages";
import SharedCollectionPage from "./pages/SharedCollectionPage";
import SoldPage from "./pages/SoldPage";
import StatusPage from "./pages/StatusPage";

interface AppState {
  user: User | null;
  setUser: (u: User | null) => void;
  coinTypes: CoinType[];
  collections: Collection[];
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
    const [types, cols] = await Promise.all([api.coinTypes(), api.collections()]);
    setCoinTypes(types);
    setCollections(cols);
  }, []);

  useEffect(() => {
    if (user) refresh();
    else {
      setCoinTypes([]);
      setCollections([]);
    }
  }, [user, refresh]);

  if (checking) return <div className="center-screen muted">Loading…</div>;

  return (
    <AppContext.Provider value={{ user, setUser, coinTypes, collections, refresh }}>
      <Routes>
        <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <LandingPage />} />
        <Route path="/login" element={user ? <Navigate to="/dashboard" /> : <LoginPage />} />
        <Route path="/signup" element={user ? <Navigate to="/dashboard" /> : <SignupPage />} />
        <Route path="/shared/:token" element={<SharedCollectionPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/collections/:typeSlug/sold" element={<SoldPage />} />
          <Route path="/collections/:typeSlug/:number" element={<CollectionPage />} />
          <Route path="/collections/:typeSlug/:number/status" element={<StatusPage />} />
          <Route path="/coins/new" element={<CoinFormPage />} />
          <Route path="/coins/:inv" element={<CoinDetailPage />} />
          <Route path="/coins/:inv/edit" element={<CoinFormPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </AppContext.Provider>
  );
}

function RequireAuth() {
  const { user } = useApp();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <Layout />;
}

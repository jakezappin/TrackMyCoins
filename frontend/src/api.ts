export type GradingService = "PCGS" | "NGC" | "ANACS" | "CACG" | "RAW";
export type CacSticker = "green" | "gold";

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

export type Finish = "MS" | "PR" | "SPR";

export interface FinishInfo {
  code: Finish;
  label: string; // "MS" | "Proof" | "Silver Proof"
  collection_type_slug: string; // e.g. "kennedy-half-dollars-proof"
  collection_type_label: string; // e.g. "Kennedy Half Dollars – Proof"
}

export interface CoinType {
  id: number;
  name: string; // singular, e.g. "Morgan Dollar"
  plural: string;
  slug: string;
  category: string;
  inventory_prefix: string;
  mint_marks: string[];
  finishes: FinishInfo[];
  metal: "gold" | "silver";
  is_type_set: boolean;
  member_ids: number[]; // type sets: series their coins can come from
}

export interface Summary {
  coin_count: number;
  total_price_paid: string;
  total_estimated_value: string; // CPG (+ toner premiums) or your own values
  total_cpg_value: string; // CPG part only
  est_wholesale_value: string;
  unpriced_count: number;
  toner_count: number;
  toner_premium_total: string;
  holder_count: number;
  holder_premium_total: string;
  custom_count: number;
}

export interface Collection {
  id: number;
  number: number;
  name: string;
  coin_type_id: number;
  coin_type_slug: string;
  finish: Finish;
  collection_type_slug: string;
  collection_type_label: string;
  created_at: string;
  last_viewed_at: string | null;
  /** Read-only public link token; null = not shared. */
  share_token: string | null;
  share_show_values: boolean;
  summary: Summary;
}

export interface ImportRow {
  row: number;
  sheet: string;
  fields: Partial<CoinFields> & Record<string, unknown>;
  valuation: Record<string, unknown>;
  errors: string[];
  description: string;
  lookup_raw: Record<string, unknown> | null;
  photo_urls: string[];
}

export interface ImportPreview {
  collection_id: number;
  rows: ImportRow[];
  ok_count: number;
  error_count: number;
}

/** What Claude read off a slab label photo. */
export interface LabelReading {
  found_label: boolean;
  grading_service: Exclude<GradingService, "RAW"> | null;
  cert_number: string | null;
  year: number | null;
  mint_mark: string | null;
  coin_type: string | null;
  denomination: string | null;
  grade_prefix: string | null;
  grade: number | null;
  grade_plus: boolean;
  grade_star: boolean;
  strike_designation: string | null;
  variety: string | null;
  vam: string | null;
  cac_sticker: CacSticker | null;
  confidence: "high" | "medium" | "low";
  notes: string | null;
  /** "barcode" = scanned (and, for PCGS, confirmed by lookup); "claude" = read from the printed label. */
  source: "barcode" | "claude";
  /** The PCGS lookup that confirmed a scanned barcode, when there was one. */
  lookup?: LookupResult | null;
}

/** A coin as a visitor to a shared link sees it: no cost, seller, notes or sale details. */
export type SharedCoin = Omit<
  CoinFields,
  "pcgs_number" | "price_paid" | "purchase_date" | "purchased_from" | "sale_price" | "sale_date" | "sold_to" | "notes"
> & {
  id: number;
  value_estimate: string | null;
  photo_urls: string[];
};

export interface SharedCollection {
  name: string;
  owner: string;
  collection_type_label: string;
  coin_type_name: string;
  metal: "silver" | "gold";
  show_values: boolean;
  coin_count: number;
  total_estimated_value: string | null;
  coins: SharedCoin[];
}

export interface CoinFields {
  year: number | null;
  mint_mark: string;
  vam: string | null;
  variety: string | null;
  pcgs_number: string | null;
  grading_service: GradingService;
  cert_number: string | null;
  grade_prefix: string | null;
  grade: number | null;
  grade_plus: boolean;
  grade_star: boolean;
  strike_designation: string | null;
  cac: boolean;
  cac_sticker: CacSticker | null;
  slab_soapbox: boolean;
  slab_ngc_fatty: boolean;
  slab_rattler: boolean;
  slab_ogh: boolean;
  gsa_hard_pack: boolean;
  gsa_soft_pack: boolean;
  ike_blue_pack: boolean;
  ike_brown_pack: boolean;
  toning_obverse: boolean;
  toning_reverse: boolean;
  toning_dual: boolean;
  toning_rainbow: boolean;
  price_paid: string | null;
  purchase_date: string | null;
  purchased_from: string | null;
  sale_price: string | null;
  sale_date: string | null;
  sold_to: string | null;
  notes: string | null;
}

export interface PriceQuote {
  id: number;
  source: string;
  value: string | null;
  grade_used: string | null;
  description: string | null;
  fetched_at: string;
}

export interface Photo {
  id: number;
  sort_order: number;
  source: string;
  url: string;
}

export interface Coin extends CoinFields {
  id: number;
  coin_type_id: number;
  collection_id: number;
  inventory_number: string;
  is_sold: boolean;
  created_at: string;
  updated_at: string;
  latest_cpg: PriceQuote | null;
  value_source: "cpg" | "custom";
  custom_value: string | null;
  toner_premium: string | null;
  holder_premium: string | null;
  value_estimate: string | null;
  latest_greysheet: PriceQuote | null;
  photo_count: number;
  thumbnail_url: string | null;
  coin_type_slug: string;
  collection_type_slug: string;
  collection_number: number;
  finish: Finish;
}

export interface AuctionSale {
  date: string; // "YYYY-MM"
  price: string;
  auctioneer: string | null;
  sale_name: string | null;
  lot: string | null;
  url: string | null;
  service: string | null;
  cert_number: string | null;
  cac: boolean;
}

export interface PcgsMarket {
  fetched_at: string;
  pcgs_number: string;
  grade: string;
  price_guide: string | null;
  population: number | null;
  pop_higher: number | null;
  coinfacts_url: string | null;
  auctions: AuctionSale[];
}

export interface CoinDetail extends Coin {
  pcgs_market: PcgsMarket | null;
  photos: Photo[];
  price_quotes: PriceQuote[];
  collection_name: string;
}

export interface LookupResult {
  grading_service: GradingService;
  cert_number: string;
  year: number | null;
  mint_mark: string | null;
  grade_prefix: string | null;
  grade: number | null;
  grade_plus: boolean;
  grade_star: boolean;
  strike_designation: string | null;
  vam: string | null;
  pcgs_number: string | null;
  cac: boolean | null;
  cac_sticker: CacSticker | null;
  description: string | null;
  image_urls: string[];
  price_guide_value: string | null;
  verify_url: string | null;
  warnings: string[];
  raw: Record<string, unknown> | null;
}

export interface StatusRow {
  label: string; // "1881-S", "1936 Boone"
  year: number;
  mint_mark: string;
  variety: string | null;
  coins: Coin[];
}

export type StatusMode = "full" | "type";

export interface CollectionStatus {
  mode: StatusMode;
  modes: StatusMode[];
  total: number;
  filled: number;
  rows: StatusRow[];
  others: Coin[];
}

export interface CatalogCandidate {
  pcgs_number: string | null;
  gsid: number;
  name: string;
  variety: string | null;
  designation: string | null;
  exact: boolean;
}

export interface CatalogMatch {
  candidates: CatalogCandidate[];
  best: CatalogCandidate | null;
  message: string | null;
}

export interface DuplicateCert {
  inventory_number: string;
  description: string;
  collection_name: string;
  coin_type_slug: string;
  collection_type_slug: string;
  collection_number: number;
}

export interface DashboardData {
  totals: Summary & { collection_count: number };
  recent_collections: Collection[];
  recent_sales: { coin: Coin; collection_name: string; collection_type_label: string; profit: string | null }[];
}

export interface SearchHit {
  coin: Coin;
  type_name: string;
  collection_name: string;
}

export interface RefreshJob {
  id: string;
  kind: string;
  scope: string;
  include_pcgs: boolean;
  total: number;
  done: number;
  updated: number;
  skipped: number;
  failed: number;
  status: "running" | "finished" | "failed";
  current: string | null;
  messages: string[];
  pcgs_stopped: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface HistoryPoint {
  date: string;
  coin_count: number;
  priced_count: number;
  cost: string;
  value: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }

  /** The existing coin, when the server rejected a duplicate cert (HTTP 409). */
  get duplicate(): DuplicateCert | null {
    return ((this.detail as { duplicate?: DuplicateCert })?.duplicate as DuplicateCert) ?? null;
  }
}

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof (detail as { message?: unknown }).message === "string") return (detail as { message: string }).message;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.filter((x) => x !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, `${res.status} ${res.statusText}`), data?.detail);
  return data as T;
}

export const api = {
  me: () => request<User>("GET", "/api/auth/me"),
  login: (email: string, password: string) => request<User>("POST", "/api/auth/login", { email, password }),
  authConfig: () => request<{ signup: "open" | "invite" | "closed" }>("GET", "/api/auth/config"),
  signup: (b: { email: string; first_name: string; last_name: string; password: string; invite_code?: string }) =>
    request<User>("POST", "/api/auth/signup", b),
  logout: () => request<void>("POST", "/api/auth/logout"),
  updateProfile: (b: { email: string; first_name: string; last_name: string; current_password?: string }) =>
    request<User>("PUT", "/api/auth/me", b),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", "/api/auth/password", { current_password, new_password }),
  certCheck: (service: GradingService, cert: string, exclude?: string | null) => {
    const qs = new URLSearchParams({ service, cert });
    if (exclude) qs.set("exclude", exclude);
    return request<{ duplicate: DuplicateCert | null }>("GET", `/api/cert-check?${qs}`);
  },

  coinTypes: () => request<CoinType[]>("GET", "/api/coin-types"),
  dashboard: () => request<DashboardData>("GET", "/api/dashboard"),
  history: (collectionId: number | null) =>
    request<HistoryPoint[]>("GET", `/api/history${collectionId == null ? "" : `?collection_id=${collectionId}`}`),
  refreshPrices: (collection_id: number | null, include_pcgs: boolean) =>
    request<RefreshJob>("POST", "/api/refresh-prices", { collection_id, include_pcgs }),
  job: (id: string) => request<RefreshJob>("GET", `/api/jobs/${id}`),
  currentJob: () => request<RefreshJob | null>("GET", "/api/jobs/current"),
  publicStats: () => request<{ series: number; collection_types: number; categories: number }>("GET", "/api/public/stats"),
  searchCoins: (q: string, limit = 8) =>
    request<SearchHit[]>("GET", `/api/search/coins?q=${encodeURIComponent(q)}&limit=${limit}`),
  soldCoins: (typeSlug: string) => request<Coin[]>("GET", `/api/coin-types/${encodeURIComponent(typeSlug)}/sold`),

  collections: () => request<Collection[]>("GET", "/api/collections"),
  collectionByNumber: (typeSlug: string, number: number) =>
    request<Collection>("GET", `/api/collections/by-number/${encodeURIComponent(typeSlug)}/${number}`),
  createCollection: (name: string, coin_type_id: number, finish: Finish) =>
    request<Collection>("POST", "/api/collections", { name, coin_type_id, finish }),
  renameCollection: (id: number, name: string) => request<Collection>("PATCH", `/api/collections/${id}`, { name }),
  deleteCollection: (id: number) => request<void>("DELETE", `/api/collections/${id}`),
  shareCollection: (id: number, showValues: boolean) =>
    request<Collection>("PUT", `/api/collections/${id}/share`, { show_values: showValues }),
  stopSharing: (id: number) => request<Collection>("DELETE", `/api/collections/${id}/share`),
  shared: (token: string) => request<SharedCollection>("GET", `/api/shared/${encodeURIComponent(token)}`),
  collectionCoins: (id: number) => request<Coin[]>("GET", `/api/collections/${id}/coins`),
  collectionStatus: (id: number, mode: StatusMode = "full") =>
    request<CollectionStatus>("GET", `/api/collections/${id}/status?mode=${mode}`),
  exportUrl: (id: number) => `/api/collections/${id}/export`,
  insuranceUrl: (collectionId: number | null) =>
    `/api/reports/insurance${collectionId == null ? "" : `?collection_id=${collectionId}`}`,

  coin: (inv: string) => request<CoinDetail>("GET", `/api/coins/${encodeURIComponent(inv)}`),
  createCoin: (b: CoinFields & { collection_id: number; coin_type_id?: number | null; lookup_raw?: unknown }) =>
    request<CoinDetail>("POST", "/api/coins", b),
  updateCoin: (inv: string, b: CoinFields & { collection_id: number; coin_type_id?: number | null }) =>
    request<CoinDetail>("PUT", `/api/coins/${encodeURIComponent(inv)}`, b),
  deleteCoin: (inv: string) => request<void>("DELETE", `/api/coins/${encodeURIComponent(inv)}`),

  importPreview: (collectionId: number, file: File) => {
    const fd = new FormData();
    fd.append("collection_id", String(collectionId));
    fd.append("file", file);
    return request<ImportPreview>("POST", "/api/import/preview", fd);
  },
  importCerts: (collectionId: number, certs: string) =>
    request<ImportPreview>("POST", "/api/import/certs", { collection_id: collectionId, certs }),
  importCommit: (collectionId: number, rows: ImportRow[], importPhotos: boolean) =>
    request<{ created: string[]; skipped: { row: number; description: string; errors: string[] }[] }>(
      "POST",
      "/api/import/commit",
      { collection_id: collectionId, rows, import_photos: importPhotos },
    ),
  readLabel: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<LabelReading>("POST", "/api/read-label", fd);
  },
  uploadPhotos: (inv: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/photos`, fd);
  },
  importPhotos: (inv: string, urls: string[]) =>
    request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/photos/import`, { urls }),
  reorderPhotos: (inv: string, photo_ids: number[]) =>
    request<CoinDetail>("PUT", `/api/coins/${encodeURIComponent(inv)}/photos/order`, { photo_ids }),
  deletePhoto: (photoId: number) => request<void>("DELETE", `/api/photos/${photoId}`),

  lookup: (service: GradingService, cert: string) =>
    request<LookupResult>(
      "GET",
      `/api/lookup?service=${encodeURIComponent(service)}&cert=${encodeURIComponent(cert)}`,
    ),
  catalogMatch: (p: {
    coin_type_id: number;
    year: number;
    mint_mark: string;
    designation?: string | null;
    finish?: Finish;
    variety?: string | null;
    gsa?: "hard" | "soft" | null;
  }) => {
    const qs = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => v != null && v !== "" && qs.set(k, String(v)));
    return request<CatalogMatch>("GET", `/api/catalog/match?${qs}`);
  },
  designations: (coinTypeId: number, finish: Finish) =>
    request<string[]>("GET", `/api/coin-types/${coinTypeId}/designations?finish=${finish}`),
  catalogSync: (coinTypeId: number) =>
    request<{ count: number; synced_at: string | null; nodes: string[] }>(
      "POST",
      `/api/coin-types/${coinTypeId}/catalog/sync`,
    ),
  getPcgs: (inv: string) => request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/pcgs`),
  setValuation: (
    inv: string,
    b: { source: "cpg" | "custom"; custom_value?: string | null; toner_premium?: string | null; holder_premium?: string | null },
  ) =>
    request<CoinDetail>("PUT", `/api/coins/${encodeURIComponent(inv)}/valuation`, b),
  getCpg: (inv: string) => request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/cpg`),
  addQuote: (inv: string, value: string, source = "CPG", description?: string) =>
    request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/price-quotes`, { value, source, description }),
  deleteQuote: (quoteId: number) => request<void>("DELETE", `/api/price-quotes/${quoteId}`),
};

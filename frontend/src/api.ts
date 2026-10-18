export type GradingService = "PCGS" | "NGC" | "ANACS" | "CACG" | "RAW";
export type CacSticker = "green" | "gold";

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  /** Details coins are valued at this % of straight-grade CPG. */
  details_pct: number;
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
  /** A mint or proof set series: ungraded, priced in OGP */
  is_set?: boolean;
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

export interface EbayItem {
  title: string;
  price: number;
  kind: "auction" | "buy_it_now";
  best_offer: boolean;
  bids: number | null;
  ends: string | null;
  url: string | null;
  image: string | null;
  cac: boolean;
}

export type EbayListings =
  | { configured: false; search_url: string }
  | {
      configured: true;
      query: string;
      search_url: string;
      total_found: number;
      items: EbayItem[];
      stats: { count: number; buy_it_now_count: number; low: number | null; median: number | null; high: number | null };
    };

export interface NgcImages {
  cert_number: string;
  /** Full-size obverse / reverse */
  urls: string[];
  previews: string[];
}

export interface ExportColumn {
  name: string;
  /** Only on the Sold sheet (sale price, sale date, ...). */
  sold_only: boolean;
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
  hints?: Record<string, string>;
  /** The collection the coin will go into, and whether that collection will be created. */
  target?: string | null;
  target_new?: boolean;
}

export interface ImportPreview {
  collection_id: number | null;
  rows: ImportRow[];
  ok_count: number;
  error_count: number;
}

export interface ImportResult {
  created: string[];
  collections: { id: number; name: string; count: number; new: boolean }[];
  skipped: { row: number; sheet: string; description: string; errors: string[] }[];
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
  details?: boolean;
  details_problem?: string | null;
  variety: string | null;
  vam: string | null;
  cac_sticker: CacSticker | null;
  confidence: "high" | "medium" | "low";
  notes: string | null;
  /** "barcode" = scanned (and, for PCGS, confirmed by lookup); "claude" = read from the printed label. */
  source: "barcode" | "claude" | "ngc_page";
  /** The PCGS lookup that confirmed a scanned barcode, when there was one. */
  lookup?: LookupResult | null;
}

/** A coin as a visitor to a shared link sees it: no cost, seller, notes or sale details. */
export type SharedCoin = Omit<
  CoinFields,
  | "pcgs_number" | "price_paid" | "purchase_value_custom" | "purchase_date" | "purchased_from" | "sale_price" | "sale_date"
  | "sold_to" | "notes"
> & {
  id: number;
  value_estimate: string | null;
  photo_urls: string[];
  thumb_url: string | null;
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
  /** Details grade: genuine but with a problem; valued at a share of straight-grade CPG. */
  details: boolean;
  details_problem: string | null;
  /** This coin's % of straight CPG (null: the owner's default). */
  details_pct: number | null;
  slab_soapbox: boolean;
  slab_ngc_fatty: boolean;
  slab_rattler: boolean;
  slab_ogh: boolean;
  gsa_hard_pack: boolean;
  gsa_soft_pack: boolean;
  ike_blue_pack: boolean;
  ike_brown_pack: boolean;
  /** Original Government Packaging */
  ogp: boolean;
  /** Mint & proof sets: in a Capital Plastics holder */
  capital_holder: boolean;
  toning_obverse: boolean;
  toning_reverse: boolean;
  toning_dual: boolean;
  toning_rainbow: boolean;
  price_paid: string | null;
  /** Your own estimated value at purchase; blank: worked out (see CoinDetail.purchase_value). */
  purchase_value_custom: string | null;
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
  /** When this price began. */
  fetched_at: string;
  /** Last time the same price was seen again. */
  confirmed_at: string | null;
}

export interface Photo {
  id: number;
  sort_order: number;
  source: string;
  url: string;
  /** Small version for strips and lists. */
  thumb_url: string;
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
  /** How a Details coin's value was worked out. */
  details_basis: string | null;
  /** A Details coin's share of CPG, before premiums. */
  details_value: string | null;
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

export interface CoinFacts {
  mintage: number | null;
  mint_location: string | null;
  metal: string | null;
  weight_g: number | null;
  diameter_mm: number | null;
  edge: string | null;
  designer: string | null;
  series: string | null;
  population: number | null;
  pop_higher: number | null;
  pop_grade: string | null;
  as_of: string | null;
  source: "pcgs_market" | "cert_lookup";
  pcgs_number: string | null;
  /** Silver/gold coins only: precious-metal content × live spot. */
  melt: { value: number; metals: { metal: string; oz: number; spot: number }[]; as_of: string | null } | null;
}

export interface GradePriceRow {
  grade: number;
  label: string;
  cpg?: string;
  wholesale?: string;
  cac_cpg?: string;
  cac_wholesale?: string;
}

export type GradePrices =
  | { rows: null }
  | {
      rows: GradePriceRow[];
      name: string | null;
      designation: string | null;
      fetched_at: string;
      wholesale_discount: number;
      has_cac: boolean;
    };

// ---- Bullion (kept apart from coins) ----
export type Metal = "silver" | "gold" | "platinum" | "palladium";

export interface BullionSummary {
  count: number;
  oz: Partial<Record<Metal, string>>;
  /** Paid per pure ounce: also the spot price where it breaks even. */
  avg_cost_oz: Partial<Record<Metal, string>>;
  value: string;
  cost: string;
  change: string;
  change_pct: number | null;
  unpriced: number;
  sold_count: number;
  realized: string;
  spot: Partial<Record<Metal, string | null>>;
  by_metal?: Partial<Record<Metal, BullionSummary>>;
}

export interface BullionCollection {
  id: number;
  name: string;
  metal: Metal;
  created_at: string;
  summary: BullionSummary;
  items?: BullionItem[];
}

export interface BullionItemIn {
  collection_id: number;
  description: string;
  packaging: "single" | "roll" | "tube" | "box";
  quantity: number;
  weight: string | null;
  weight_unit: "ozt" | "g" | "kg";
  purity: string;
  face_value: string | null;
  price_paid: string | null;
  purchase_date: string | null;
  purchased_from: string | null;
  sale_price: string | null;
  sale_date: string | null;
  sold_to: string | null;
  notes: string | null;
}

export interface BullionItem extends BullionItemIn {
  id: number;
  inventory_number: string;
  collection_name: string;
  metal: Metal;
  is_sold: boolean;
  created_at: string;
  oz: string;
  spot_now: string | null;
  value_now: string | null;
  spot_at_purchase: string | null;
  value_at_purchase: string | null;
  premium_pct: number | null;
  change: string | null;
  change_pct: number | null;
  photos: { id: number; url: string; thumb_url: string }[];
  thumbnail_url: string | null;
  /** Days from purchase to sale (or today); over a year is long-term. */
  held_days: number;
  long_term: boolean;
}

export interface BullionSearchHit {
  inventory_number: string;
  description: string;
  metal: Metal;
  collection_name: string;
  oz: string;
  is_sold: boolean;
  thumbnail_url: string | null;
}

export interface BullionImportRow {
  row: number;
  sheet: string;
  fields: Partial<BullionItemIn> & { oz?: string };
  errors: string[];
}

export interface BullionMeta {
  metals: Metal[];
  purities: Record<Metal, string[]>;
  units: string[];
  packaging: string[];
  face_purities: string[];
  spot: Partial<Record<Metal, string | null>>;
}

/** One mint or proof set from the catalog (the coin form's Set picker). */
export interface SetOption {
  gsid: number;
  year: number;
  mint_mark: string;
  variety: string | null;
  pcgs_number: string | null;
  name: string; // checklist line: "" for the year's main set
  label: string;
  extra: boolean;
  silver_oz: number | null;
}

export interface PriceData {
  cpg_prices: number;
  cpg_issues: number;
  cpg_since: string | null;
  auction_sales: number;
  auction_issues: number;
  auction_since: string | null;
  guide_values: number;
  database_mb: number;
  last_sheet_update: string | null;
  last_auction_update: string | null;
}

/** Estimated value at purchase and where it came from. */
export interface PurchaseValue {
  value: string | null;
  source: "custom" | "cpg" | "cpg_history" | "auctions" | "paid" | null;
  detail: string;
  /** PCGS auction sales not looked up yet (the coin page asks for them). */
  pending: boolean;
}

export interface CoinDetail extends Coin {
  purchase_value: PurchaseValue | null;
  /** Mint & proof sets: silver content and melt value */
  set_melt: { oz: number; spot: number | null; value: number | null; as_of: string | null } | null;
  facts: CoinFacts | null;
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
  /** Overdate / over-mintmark from the coin name, e.g. "1880/79", "O/S". */
  variety: string | null;
  pcgs_number: string | null;
  cac: boolean | null;
  cac_sticker: CacSticker | null;
  details?: boolean;
  details_problem?: string | null;
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
  /** Mint & proof sets: specialty sets, listed but not counted */
  extras?: StatusRow[];
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

export interface WantItem {
  id: number;
  label: string;
  collection_id: number | null;
  collection_name: string | null;
  coin_type_id: number;
  finish: Finish;
  year: number;
  mint_mark: string;
  variety: string | null;
  grade_prefix: string | null;
  grade: number | null;
  target_label: string | null;
  max_price: string | null;
  notes: string | null;
  cpg: string | null;
  priceable: boolean;
  owned: {
    inventory_number: string;
    grade: number | null;
    grade_prefix: string | null;
    grade_plus: boolean;
    grade_star: boolean;
    strike_designation: string | null;
    grading_service: GradingService;
    details?: boolean;
    meets_target: boolean;
  } | null;
}

export type PreciousMetal = "gold" | "silver" | "platinum" | "palladium";

export interface SpotCard {
  metal: PreciousMetal;
  price: number | null;
  live: boolean;
  as_of: string | null;
  prev_close: number | null;
  prev_day: string | null;
  /** Weekend: the change shown is the last trading day's. */
  market_closed: boolean;
  change: number | null;
  change_pct: number | null;
  changes: { "1w": number | null; "1m": number | null; ytd: number | null; "1y": number | null };
  high_52w: number | null;
  low_52w: number | null;
}

export interface MeltRow {
  key: string;
  group: string;
  name: string;
  years: string;
  face: number;
  metal: PreciousMetal | "copper";
  amount: number;
  unit: "ozt" | "lb";
  composition: string;
  melt: number | null;
  x_face: number | null;
}

export interface MetalsOverview {
  spot: SpotCard[];
  copper: { price: number | null; as_of: string | null };
  ratio: {
    value: number | null;
    signal: "trade_gold" | "trade_silver" | "neutral" | null;
    average?: number;
    high?: number;
    low?: number;
    years?: number;
    percentile?: number;
    min?: number;
    max?: number;
  };
  coins: MeltRow[];
  junk_oz_per_dollar: number;
  holdings: {
    metals: { metal: PreciousMetal; bullion_oz: number; coin_oz: number; oz: number; value: number | null }[];
    coins_counted: number;
    coins_total: number;
  };
}

export type MetalRange = "1m" | "6m" | "1y" | "5y" | "10y" | "all";

export interface WantIn {
  collection_id?: number | null;
  coin_type_id?: number | null;
  finish?: Finish;
  year: number;
  mint_mark: string;
  variety?: string | null;
  grade_prefix?: string | null;
  grade?: number | null;
  max_price?: string | null;
  notes?: string | null;
}

export interface UpgradeItem {
  label: string;
  year: number;
  mint_mark: string;
  variety: string | null;
  coin: {
    inventory_number: string;
    grade: number | null;
    grade_prefix: string | null;
    grade_plus: boolean;
    grade_star: boolean;
    strike_designation: string | null;
    cac: boolean;
    details?: boolean;
    details_problem?: string | null;
  };
  current_value: string | null;
  next_grade: number;
  next_label: string;
  next_cpg: string;
  cost: string | null;
  pct: number | null;
}

export interface Upgrades {
  items: UpgradeItem[];
  unpriced: string[];
  at_top: string[];
}

export interface Mover {
  coin: Coin;
  old: string;
  new: string;
  change: string;
  pct: number;
  changed_on: string;
}

export interface DashboardData {
  totals: Summary & { collection_count: number };
  recent_collections: Collection[];
  recent_sales: { coin: Coin; collection_name: string; collection_type_label: string; profit: string | null }[];
  gainers: Mover[];
  decliners: Mover[];
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
  /** Some coins weren't priced yet on this day; their first recorded estimate stands in. */
  backfilled: boolean;
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

const FIELD_LABELS: Record<string, string> = {
  year: "Year",
  mint_mark: "Mint mark",
  grade: "Grade",
  grade_prefix: "Grade",
  cert_number: "Cert number",
  pcgs_number: "PCGS #",
  price_paid: "Price paid",
  purchase_value_custom: "Est. value at purchase",
  purchase_date: "Purchase date",
  sale_price: "Sale price",
  sale_date: "Sale date",
  custom_value: "Your estimated value",
  toner_premium: "Toner premium",
  holder_premium: "Holder premium",
  value: "Value",
  notes: "Notes",
};

/** Pydantic's wording, in plain English. */
function plain(msg: string): string {
  const rules: [RegExp, string][] = [
    [/^Input should be a valid (decimal|number|integer).*/i, "must be a number"],
    [/^Input should be greater than or equal to 0.*/i, "can't be negative"],
    [/^Input should be greater than or equal to (\d+).*/i, "must be at least $1"],
    [/^Input should be less than or equal to (\d+).*/i, "must be at most $1"],
    [/^Decimal input should have no more than 2 decimal places.*/i, "use dollars and cents (2 decimal places)"],
    [/^Decimal input should have no more than \d+ digits.*/i, "is too large"],
    [/^Input should be a finite number.*/i, "must be a number"],
    [/^Input should be a valid date.*/i, "isn't a real date"],
    [/^String should have at most (\d+) characters.*/i, "is too long (at most $1 characters)"],
    [/^String should have at least 1 character.*/i, "is required"],
    [/^Field required.*/i, "is required"],
  ];
  for (const [re, out] of rules) if (re.test(msg)) return msg.replace(re, out);
  return msg;
}

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof (detail as { message?: unknown }).message === "string") return (detail as { message: string }).message;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const msg = plain((d.msg ?? "").replace(/^(Value error|Assertion failed), /, ""));
        const field = d.loc?.filter((x) => x !== "body" && typeof x === "string").pop() as string | undefined;
        // Our own messages already name the field ("The sale date is before..."); pydantic's need a label.
        const own = /^[A-Z]/.test(msg) && !/^(Input|Value|String|Field|Decimal|Date)\b/.test(msg);
        return field && !own ? `${FIELD_LABELS[field] ?? field.replace(/_/g, " ")}: ${msg}` : msg;
      })
      .join(" ");
  }
  return fallback;
}

export interface Attachment {
  id: number;
  name: string;
  content_type: string;
  size: number;
  created_at: string;
  url: string;
}

const attachmentBase = (kind: "coin" | "bullion") => (kind === "bullion" ? "/api/bullion/items" : "/api/coins");

// When the session runs out the app goes back to the login page instead of every page saying "Not logged in".
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}
// Where a 401 is an ordinary answer (wrong password, not signed in yet), not an expired session.
const AUTH_ANSWERS = ["/api/auth/login", "/api/auth/me", "/api/auth/signup", "/api/auth/password"];

function checkSession(path: string, status: number) {
  if (status === 401 && !AUTH_ANSWERS.some((p) => path.startsWith(p))) onUnauthorized?.();
}

const TIMEOUT_MS = 60_000;
const UPLOAD_TIMEOUT_MS = 5 * 60_000; // imports and photo uploads can take a while on a phone connection

async function send(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(path, { ...init, signal: ctrl.signal });
  } catch (e) {
    if (ctrl.signal.aborted) throw new ApiError(0, "The server took too long to answer. Check your connection and try again.");
    throw new ApiError(0, "Couldn't reach the server. Check your connection and try again.", e);
  } finally {
    window.clearTimeout(timer);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await send(path, init, body instanceof FormData || path.includes("/import") ? UPLOAD_TIMEOUT_MS : TIMEOUT_MS);
  checkSession(path, res.status);
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, `${res.status} ${res.statusText}`), data?.detail);
  return data as T;
}

/** Download a report or export: an error comes back as a message, never saved as the file. */
export async function downloadFile(url: string, fallbackName = "download"): Promise<void> {
  const res = await send(url, { credentials: "same-origin" }, UPLOAD_TIMEOUT_MS);
  checkSession(url, res.status);
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, errorMessage(data, `${res.status} ${res.statusText}`), data?.detail);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  const name = star ? decodeURIComponent(star[1]) : plain ? plain[1] : fallbackName;
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 10_000);
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
  setPreferences: (b: { details_pct: number }) => request<User>("PUT", "/api/auth/preferences", b),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("POST", "/api/auth/password", { current_password, new_password }),
  certCheck: (service: GradingService, cert: string, exclude?: string | null) => {
    const qs = new URLSearchParams({ service, cert });
    if (exclude) qs.set("exclude", exclude);
    return request<{ duplicate: DuplicateCert | null }>("GET", `/api/cert-check?${qs}`);
  },

  coinTypes: () => request<CoinType[]>("GET", "/api/coin-types"),
  metals: () => request<MetalsOverview>("GET", "/api/metals"),
  metalHistory: (series: PreciousMetal | "ratio", range: MetalRange) =>
    request<{ date: string; value: number }[]>("GET", `/api/metals/history?series=${series}&range=${range}`),
  dashboard: () => request<DashboardData>("GET", "/api/dashboard"),
  coinHistory: (inv: string) => request<HistoryPoint[]>("GET", `/api/coins/${encodeURIComponent(inv)}/history`),
  history: (collectionId: number | null) =>
    request<HistoryPoint[]>("GET", `/api/history${collectionId == null ? "" : `?collection_id=${collectionId}`}`),
  refreshAllowance: () =>
    request<{ limit: number; used: number; left: number; next_available_at: string | null }>("GET", "/api/refresh-prices/allowance"),
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
  exportColumns: () => request<ExportColumn[]>("GET", "/api/reports/export-columns"),
  insuranceUrl: (collectionId: number | null) =>
    `/api/reports/insurance${collectionId == null ? "" : `?collection_id=${collectionId}`}`,

  coin: (inv: string) => request<CoinDetail>("GET", `/api/coins/${encodeURIComponent(inv)}`),
  createCoin: (b: CoinFields & { collection_id: number; coin_type_id?: number | null; lookup_raw?: unknown }) =>
    request<CoinDetail>("POST", "/api/coins", b),
  updateCoin: (inv: string, b: CoinFields & { collection_id: number; coin_type_id?: number | null }) =>
    request<CoinDetail>("PUT", `/api/coins/${encodeURIComponent(inv)}`, b),
  deleteCoin: (inv: string) => request<void>("DELETE", `/api/coins/${encodeURIComponent(inv)}`),

  /** collectionId null: sort each coin into the collection for its series. */
  importPreview: (collectionId: number | null, file: File) => {
    const fd = new FormData();
    if (collectionId !== null) fd.append("collection_id", String(collectionId));
    fd.append("file", file);
    return request<ImportPreview>("POST", "/api/import/preview", fd);
  },
  importCerts: (collectionId: number | null, certs: string) =>
    request<ImportPreview>("POST", "/api/import/certs", { collection_id: collectionId, certs }),
  importCommit: (collectionId: number | null, rows: ImportRow[], importPhotos: boolean) =>
    request<ImportResult>(
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
  features: () => request<{ ebay: boolean }>("GET", "/api/features"),
  gradePrices: (inv: string) => request<GradePrices>("GET", `/api/coins/${encodeURIComponent(inv)}/grade-prices`),
  wants: () => request<WantItem[]>("GET", "/api/wants"),
  addWant: (w: WantIn) => request<WantItem>("POST", "/api/wants", w),
  updateWant: (id: number, w: WantIn) => request<WantItem>("PUT", `/api/wants/${id}`, w),
  deleteWant: (id: number) => request<void>("DELETE", `/api/wants/${id}`),
  priceWant: (id: number) => request<WantItem>("POST", `/api/wants/${id}/price`),
  upgrades: (collectionId: number) => request<Upgrades>("GET", `/api/collections/${collectionId}/upgrades`),
  priceData: () => request<PriceData>("GET", "/api/price-data"),
  bullionMeta: () => request<BullionMeta>("GET", "/api/bullion/meta"),
  bullionCollections: () => request<BullionCollection[]>("GET", "/api/bullion/collections"),
  bullionCollection: (id: number) => request<BullionCollection>("GET", `/api/bullion/collections/${id}`),
  createBullionCollection: (name: string, metal: Metal) =>
    request<BullionCollection>("POST", "/api/bullion/collections", { name, metal }),
  renameBullionCollection: (id: number, name: string) =>
    request<BullionCollection>("PUT", `/api/bullion/collections/${id}`, { name }),
  deleteBullionCollection: (id: number) => request<void>("DELETE", `/api/bullion/collections/${id}`),
  bullionCollectionHistory: (id: number) => request<HistoryPoint[]>("GET", `/api/bullion/collections/${id}/history`),
  bullionSummary: () => request<BullionSummary>("GET", "/api/bullion/summary"),
  bullionHistory: () => request<HistoryPoint[]>("GET", "/api/bullion/history"),
  bullionItem: (inv: string) => request<BullionItem>("GET", `/api/bullion/items/${encodeURIComponent(inv)}`),
  createBullionItem: (b: BullionItemIn) => request<BullionItem>("POST", "/api/bullion/items", b),
  updateBullionItem: (inv: string, b: BullionItemIn) =>
    request<BullionItem>("PUT", `/api/bullion/items/${encodeURIComponent(inv)}`, b),
  deleteBullionItem: (inv: string) => request<void>("DELETE", `/api/bullion/items/${encodeURIComponent(inv)}`),
  bullionItemHistory: (inv: string) =>
    request<HistoryPoint[]>("GET", `/api/bullion/items/${encodeURIComponent(inv)}/history`),
  sellBullion: (inv: string, b: { quantity?: number; face_value?: string; sale_price: string; sale_date: string; sold_to?: string | null }) =>
    request<{ sold: string; kept: string | null }>("POST", `/api/bullion/items/${encodeURIComponent(inv)}/sell`, b),
  uploadBullionPhotos: (inv: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<BullionItem>("POST", `/api/bullion/items/${encodeURIComponent(inv)}/photos`, fd);
  },
  deleteBullionPhoto: (id: number) => request<void>("DELETE", `/api/bullion/photos/${id}`),
  searchBullion: (q: string) => request<BullionSearchHit[]>("GET", `/api/bullion/search?q=${encodeURIComponent(q)}`),
  bullionExportUrl: (collectionId: number | null) =>
    collectionId == null ? "/api/bullion/export" : `/api/bullion/collections/${collectionId}/export`,
  bullionTemplateUrl: "/api/bullion/import/template",
  bullionImportPreview: (collectionId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ rows: BullionImportRow[]; ok_count: number; error_count: number }>(
      "POST", `/api/bullion/collections/${collectionId}/import/preview`, fd);
  },
  bullionImportCommit: (collectionId: number, rows: BullionImportRow[]) =>
    request<{ created: string[]; skipped: { row: number; sheet: string; description: string; errors: string[] }[] }>(
      "POST", `/api/bullion/collections/${collectionId}/import/commit`, { rows }),
  sets: (coinTypeId: number, year?: number) =>
    request<SetOption[]>("GET", `/api/coin-types/${coinTypeId}/sets${year ? `?year=${year}` : ""}`),
  fillPurchaseValue: (inv: string) =>
    request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/purchase-value`),
  moveTargets: (inv: string) =>
    request<{ id: number; name: string; finish: string }[]>("GET", `/api/coins/${encodeURIComponent(inv)}/move-targets`),
  moveCoin: (inv: string, collectionId: number) =>
    request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/move`, { collection_id: collectionId }),
  ebayListings: (inv: string) => request<EbayListings>("GET", `/api/coins/${encodeURIComponent(inv)}/ebay`),
  ngcImages: (link: string) => request<NgcImages>("GET", `/api/ngc-images?link=${encodeURIComponent(link)}`),
  ngcPage: (d: { cert: string; grade: string | null; images: string[]; text: string }) =>
    request<{ reading: LabelReading; photos: { urls: string[]; previews: string[] } }>("POST", "/api/ngc-page", d),
  importPhotos: (inv: string, urls: string[]) =>
    request<CoinDetail>("POST", `/api/coins/${encodeURIComponent(inv)}/photos/import`, { urls }),
  reorderPhotos: (inv: string, photo_ids: number[]) =>
    request<CoinDetail>("PUT", `/api/coins/${encodeURIComponent(inv)}/photos/order`, { photo_ids }),
  /** Receipts & documents of a coin, or (kind "bullion") of a bullion item. */
  attachments: (inv: string, kind: "coin" | "bullion" = "coin") =>
    request<Attachment[]>("GET", `${attachmentBase(kind)}/${encodeURIComponent(inv)}/attachments`),
  uploadAttachments: (inv: string, files: File[], kind: "coin" | "bullion" = "coin") => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<Attachment[]>("POST", `${attachmentBase(kind)}/${encodeURIComponent(inv)}/attachments`, fd);
  },
  /** `url` is the attachment's own address (coin or bullion). */
  deleteAttachment: (url: string) => request<void>("DELETE", url),
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
    request<{ count: number; synced_at: string | null; nodes: number[] }>(
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

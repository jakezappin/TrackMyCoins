import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useUnsavedGuard } from "../components/useUnsavedGuard";
import {
  api,
  ApiError,
  type CatalogCandidate,
  type CatalogHit,
  type Coin,
  type CoinFields,
  type Finish,
  type GradingCompany,
  type DuplicateCert,
  type GradingService,
  type LabelReading,
  type LookupResult,
  type SetOption,
  type SubmissionSummary,
} from "../api";
import NgcPhotoLink from "../components/NgcPhotoLink";
import PhotoButtons from "../components/PhotoButtons";
import { clearCoinDraft, NGC_BOOKMARK_ENABLED, ngcCertUrl, readCoinDraft, readNgcHandoff, saveCoinDraft } from "../ngcButton";
import DuplicateCertModal from "../components/DuplicateCertModal";
import StoragePicker from "../components/StoragePicker";
import CoinSearch from "../components/CoinSearch";
import { COMPANIES as GRADING_COMPANIES } from "./GradingPage";
import { useApp, useNavCollection } from "../App";
import { coinPath, collectionPath, collectionsBySeries, DETAILS_PROBLEMS, FINISH_LABEL, money, parseMoney, todayISO } from "../format";

const EMPTY: CoinFields = {
  year: null,
  mint_mark: "P",
  vam: null,
  variety: null,
  pcgs_number: null,
  grading_service: "PCGS",
  cert_number: null,
  grade_prefix: "MS",
  grade: null,
  grade_plus: false,
  grade_star: false,
  strike_designation: null,
  cac: false,
  cac_sticker: null,
  details: false,
  details_problem: null,
  details_pct: null,
  location: "inventory",
  storage_id: null,
  storage_position: null,
  slab_soapbox: false,
  slab_ngc_fatty: false,
  slab_rattler: false,
  slab_ogh: false,
  gsa_hard_pack: false,
  gsa_soft_pack: false,
  ike_blue_pack: false,
  ike_brown_pack: false,
  ogp: false,
  capital_holder: false,
  toning_obverse: false,
  toning_reverse: false,
  toning_dual: false,
  toning_rainbow: false,
  toning_rim: false,
  is_error: false,
  error_description: null,
  price_paid: null,
  asking_price: null,
  purchase_value_custom: null,
  purchase_date: null,
  purchased_from: null,
  sale_price: null,
  sale_date: null,
  sold_to: null,
  notes: null,
};

const SERVICES: GradingService[] = ["PCGS", "NGC", "ANACS", "CACG", "ICG", "RAW"];
const CIRC_PREFIXES = ["MS", "SP", "AU", "XF", "VF", "F", "VG", "G", "AG", "FR", "PO"];

/** A grade typed the way NGC and the others write it: "MS64", "64", "AU 58", "PF69", "64+", "65★". */
function parseGrade(s: string): { prefix: string | null; grade: number; plus: boolean; star: boolean } | null {
  const m = /^\s*(MS|SP|PR|PF|AU|XF|EF|VF|F|VG|G|AG|FR|PO|P)?\s*-?\s*(\d{1,2})\s*(\+)?\s*(\*|★)?\s*$/i.exec(s);
  if (!m) return null;
  const grade = Number(m[2]);
  if (grade < 1 || grade > 70) return null;
  const p = m[1]?.toUpperCase() ?? null;
  const prefix = p === "PF" ? "PR" : p === "EF" ? "XF" : p === "P" ? "PO" : p;
  return { prefix, grade, plus: Boolean(m[3]), star: Boolean(m[4]) };
}
// Used until the catalog's designations for the series load (or if it can't be reached).
const FALLBACK_DESIGNATIONS: Record<string, string[]> = {
  MS: ["PL", "DMPL", "RD", "RB", "BN", "FB", "FS", "FH"],
  PR: ["CAM", "DCAM", "RD", "RB", "BN"],
};
const VAM_SERIES = ["morgan-dollars", "peace-dollars"];
// Series sold by the GSA in its hard and soft pack holders.
const GSA_SERIES = ["morgan-dollars", "peace-dollars"];
const OGP_SERIES = [
  "modern-commemorative-halves",
  "modern-commemorative-dollars",
  "modern-morgan-dollars",
  "modern-peace-dollars",
  "american-silver-eagles",
  "gold-eagles-5",
  "gold-eagles-10",
  "gold-eagles-25",
  "gold-eagles-50",
];
type PackKey = "gsa_hard_pack" | "gsa_soft_pack" | "ike_blue_pack" | "ike_brown_pack" | "ogp" | "capital_holder";
const VARIETY_HINTS: Record<string, string> = {
  "classic-commemoratives": "e.g. Alabama, Boone",
  "washington-quarters": "Design from 1999 on, e.g. Delaware, Yellowstone",
  "morgan-dollars": "e.g. 8TF, 1880/79 (overdate), O/S (over-mintmark)",
};

function verifyUrl(service: GradingService, cert: string, grade: number | null): string | null {
  if (!cert && service !== "ANACS" && service !== "CACG" && service !== "ICG") return null;
  switch (service) {
    case "PCGS":
      return `https://www.pcgs.com/cert/${encodeURIComponent(cert)}`;
    case "NGC":
      return ngcCertUrl(cert, grade);
    case "ANACS":
      // ANACS's lookup form; it can't be prefilled from the address.
      return "https://portal.anacs.com/Verify/CertVerification.aspx";
    case "ICG":
      // ICG's verification page (behind a reCAPTCHA; the serial is typed there).
      return "https://www.icgcoin.com/verification/";
    case "CACG":
      return cert ? `https://www.cacgrading.com/lookup/${encodeURIComponent(cert)}` : "https://www.cacgrading.com/lookup";
    default:
      return null;
  }
}

export default function CoinFormPage() {
  const params = useParams();
  const editInv = params.inv ?? null;
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { collections, coinTypes, refresh, user, loaded, loadError } = useApp();

  const [form, setForm] = useState<CoinFields>(EMPTY);
  const [collectionId, setCollectionId] = useState<number | null>(Number(search.get("collection")) || null);
  const [inventoryNumber, setInventoryNumber] = useState<string | null>(null);
  const [memberTypeId, setMemberTypeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(editInv !== null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookup, setLookup] = useState<LookupResult | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [importUrls, setImportUrls] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [findBusy, setFindBusy] = useState(false);
  const [findMsg, setFindMsg] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CatalogCandidate[]>([]);
  const location = useLocation();
  const [ngcHandoff] = useState(() => (editInv ? null : readNgcHandoff(location.hash)));
  // What the user had typed before going to NGC in this tab.
  const [draft] = useState(() =>
    ngcHandoff ? readCoinDraft<{ form: CoinFields; collectionId: number | null; memberTypeId: number | null }>() : null,
  );
  const [ngcState, setNgcState] = useState<"idle" | "busy" | "done">(ngcHandoff ? "busy" : "idle");
  const [ngcPreviews, setNgcPreviews] = useState<string[]>([]);
  const [cacNote, setCacNote] = useState<string | null>(null);
  const [showPaste, setShowPaste] = useState(false);
  const [labelBusy, setLabelBusy] = useState(false);
  // Unsaved-changes guard: compare with the form as loaded (or empty, for a new coin).
  const [baseline, setBaseline] = useState<string | null>(editInv ? null : JSON.stringify(EMPTY));
  const leaving = useRef(false);
  const submitting = useRef(false);
  // Choices kept outside `form` (collection, an error coin's value, the At Grading submission) count as edits too.
  const [touchedExtra, setTouchedExtra] = useState(false);
  const dirty =
    baseline !== null && (JSON.stringify(form) !== baseline || files.length > 0 || importUrls.length > 0 || touchedExtra);
  /** A change the form makes itself (a proof collection's PR prefix, a set's OGP): if nothing has been typed yet,
   * it doesn't count as an unsaved edit. */
  const autoAdjust = (fn: (f: CoinFields) => CoinFields) =>
    setForm((f) => {
      const next = fn(f);
      if (next !== f) setBaseline((b) => (b === JSON.stringify(f) ? JSON.stringify(next) : b));
      return next;
    });
  useUnsavedGuard(dirty, "You have unsaved changes to this coin. Leave without saving?", leaving);
  const [labelError, setLabelError] = useState<string | null>(null);
  const [label, setLabel] = useState<LabelReading | null>(null);
  const [dup, setDup] = useState<{ service: string; cert: string; duplicate: DuplicateCert } | null>(null);
  // At Grading: which submission (an open one, or "new" for a new one with this company).
  const [grading, setGrading] = useState<GradingPick>({ submission: "", company: "NGC", expected: "", declared: "" });
  const [currentGrading, setCurrentGrading] = useState<Coin["grading"]>(null);
  const [errorValue, setErrorValue] = useState(""); // error coins: the owner's estimated value
  const [gradeText, setGradeText] = useState<string | null>(null); // the grade beside the cert, while it's typed

  useEffect(() => {
    if (editInv === null) return;
    api
      .coin(editInv)
      .then((c) => {
        const fields = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, c[k as keyof CoinFields]])) as unknown as CoinFields;
        setForm(fields);
        setBaseline(JSON.stringify(fields));
        restoreExpiredDraft(fields);
        setCollectionId(c.collection_id);
        setMemberTypeId(c.coin_type_id);
        setInventoryNumber(c.inventory_number);
        setCurrentGrading(c.grading);
        if (c.is_error && c.value_source === "custom") setErrorValue(c.custom_value ?? "");
        if (c.grading) setGrading((g) => ({ ...g, submission: String(c.grading!.id), expected: c.grading!.expected_grade ?? "" }));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [editInv]);

  // Picked in the coin search with no collection of that series yet: one is made when the coin is saved.
  const [newCollection, setNewCollection] = useState<{ coin_type_id: number; finish: Finish; label: string } | null>(null);

  // Default to the first collection when adding without one selected.
  useEffect(() => {
    if (collectionId === null && !newCollection && collections.length) setCollectionId(collections[0].id);
  }, [collections, collectionId, newCollection]);

  const collection = collections.find((c) => c.id === collectionId);
  // In a type set (e.g. Gold Type Set) each coin comes from one of the set's member series, chosen below.
  const collectionType = coinTypes.find((t) => t.id === (collection?.coin_type_id ?? newCollection?.coin_type_id));
  const isTypeSet = Boolean(collectionType?.is_type_set);
  const memberTypes = isTypeSet ? coinTypes.filter((t) => collectionType!.member_ids.includes(t.id)) : [];
  const coinType = isTypeSet ? coinTypes.find((t) => t.id === memberTypeId) : collectionType ?? coinTypes[0];
  const finish = collection?.finish ?? newCollection?.finish ?? "MS";
  const isProof = finish !== "MS";
  const isRaw = form.grading_service === "RAW";
  // Mint & proof sets: not graded; pick the set, keep it in OGP (or a Capital holder).
  const isSetSeries = Boolean(coinType?.is_set);
  useNavCollection("coin", collectionId);
  const wasSet = useRef(false);
  useEffect(() => {
    if (isSetSeries) {
      wasSet.current = true;
      autoAdjust((f) => ({ ...f, grading_service: "RAW", cert_number: null, ...(editInv ? {} : { ogp: true }) }));
    } else if (wasSet.current && !editInv) {
      // Switched from a Mint Sets collection to a coin series: back to the usual graded-coin defaults.
      wasSet.current = false;
      autoAdjust((f) => ({ ...f, grading_service: EMPTY.grading_service, ogp: false, capital_holder: false }));
    }
  }, [isSetSeries, editInv]); // eslint-disable-line react-hooks/exhaustive-deps
  // Another collection: keep the mint only if this series was struck there, and the series only if the type set
  // includes it (otherwise the menus show one thing and the save sends another).
  useEffect(() => {
    if (!coinType) return;
    const marks = coinType.mint_marks.length ? coinType.mint_marks : ["P"];
    if (!marks.includes(form.mint_mark)) autoAdjust((f) => ({ ...f, mint_mark: marks[0] }));
  }, [coinType?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (isTypeSet && memberTypeId != null && !collectionType!.member_ids.includes(memberTypeId)) setMemberTypeId(null);
  }, [collectionType?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // Packaging checkboxes that apply to this series/finish: [field, label, the field it excludes].
  const packaging: [PackKey, string, PackKey | null][] = [];
  if (coinType && GSA_SERIES.includes(coinType.slug)) {
    packaging.push(["gsa_hard_pack", "GSA Hard Pack", "gsa_soft_pack"], ["gsa_soft_pack", "GSA Soft Pack", "gsa_hard_pack"]);
  }
  if (coinType?.slug === "ike-dollars") {
    packaging.push(isProof ? ["ike_brown_pack", "Brown Pack (40% silver proof)", null] : ["ike_blue_pack", "Blue Pack (40% silver)", null]);
  }
  // Still in its Original Government Packaging: modern commemoratives, modern Morgans and Peace dollars, Silver and
  // Gold Eagles, and Blue / Brown Pack Ikes.
  if (isSetSeries) {
    packaging.push(["ogp", "OGP (original government packaging)", null], ["capital_holder", "Capital Holder", null]);
  } else if (
    (coinType && OGP_SERIES.includes(coinType.slug)) ||
    (coinType?.slug === "ike-dollars" && (form.ike_blue_pack || form.ike_brown_pack || form.ogp))
  ) {
    packaging.push(["ogp", "OGP (original government packaging)", null]);
  }
  // When editing, a coin can only move to collections of its own series, or type sets that include it.
  const collectionGroups = useMemo(() => {
    const own = memberTypeId;
    const fits = (c: (typeof collections)[number]) => {
      const t = coinTypes.find((x) => x.id === c.coin_type_id);
      return c.coin_type_id === own || Boolean(t?.is_type_set && own != null && t.member_ids.includes(own));
    };
    const pool = editInv && own != null ? collections.filter(fits) : collections;
    return collectionsBySeries(coinTypes, pool);
  }, [collections, coinTypes, memberTypeId, editInv]);

  // Proof collections take PR grades; business-strike collections take MS and circulated grades.
  useEffect(() => {
    if (!collection) return;
    autoAdjust((f) => {
      if (isProof && f.grade_prefix !== "PR") return { ...f, grade_prefix: "PR" };
      if (!isProof && f.grade_prefix === "PR") return { ...f, grade_prefix: "MS" };
      return f;
    });
  }, [collection, isProof]); // eslint-disable-line react-hooks/exhaustive-deps

  // Designations that exist for this series and finish, from the Greysheet catalog.
  const [designations, setDesignations] = useState<string[] | null>(null);
  useEffect(() => {
    if (!coinType) return;
    let cancelled = false;
    setDesignations(null);
    api
      .designations(coinType.id, finish)
      .then((d) => !cancelled && setDesignations(d))
      .catch(() => !cancelled && setDesignations(FALLBACK_DESIGNATIONS[isProof ? "PR" : "MS"]));
    return () => {
      cancelled = true;
    };
  }, [coinType, finish, isProof]);
  const designationOptions = useMemo(() => {
    const opts = designations ?? FALLBACK_DESIGNATIONS[isProof ? "PR" : "MS"];
    return form.strike_designation && !opts.includes(form.strike_designation) ? [...opts, form.strike_designation] : opts;
  }, [designations, isProof, form.strike_designation]);

  function setRaw(raw: boolean) {
    setForm((f) =>
      raw
        ? {
            ...f,
            grading_service: "RAW",
            cert_number: null,
            cac: false,
            cac_sticker: null,
            grade_plus: false,
            grade_star: false,
            slab_soapbox: false,
            slab_ngc_fatty: false,
            slab_rattler: false,
            slab_ogh: false,
          }
        : { ...f, grading_service: "PCGS" },
    );
    setLookup(null);
    setLookupError(null);
  }

  function set<K extends keyof CoinFields>(key: K, value: CoinFields[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }
  const text = (key: keyof CoinFields) => ({
    value: (form[key] as string | number | null) ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      set(key, (e.target.value === "" ? null : e.target.value) as never),
  });
  /** A money field: shows what was typed, and tidies "1,250" to "1250.00" on leaving the field. */
  const money_ = (key: "price_paid" | "sale_price" | "purchase_value_custom" | "asking_price") => ({
    value: (form[key] as string | null) ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(key, (e.target.value === "" ? null : e.target.value) as never),
    onBlur: () => {
      const r = parseMoney(form[key]);
      if ("value" in r) set(key, r.value as never);
    },
    "aria-invalid": "error" in parseMoney(form[key]),
  });
  const check = (key: keyof CoinFields) => ({
    checked: Boolean(form[key]),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(key, e.target.checked as never),
  });

  /** Warn (and return true) if this cert is already on hand in one of the user's collections. */
  async function checkDuplicate(service: GradingService = form.grading_service, certIn = form.cert_number): Promise<boolean> {
    const cert = certIn?.trim();
    if (!cert || service === "RAW") return false;
    try {
      const { duplicate } = await api.certCheck(service, cert, editInv);
      if (duplicate) {
        setDup({ service, cert, duplicate });
        return true;
      }
    } catch {
      // The save will still be checked by the server.
    }
    return false;
  }

  async function doLookup(service: GradingService = form.grading_service, cert = form.cert_number) {
    if (!cert) return;
    if (await checkDuplicate(service, cert)) return;
    setLookupBusy(true);
    setLookupError(null);
    setLookup(null);
    try {
      applyLookup(await api.lookup(service, cert));
    } catch (e) {
      setLookupError((e as Error).message);
    } finally {
      setLookupBusy(false);
    }
  }

  function applyLookup(r: LookupResult) {
    setLookup(r);
    setForm((f) => ({
      ...f,
      cert_number: r.cert_number,
      year: r.year ?? f.year,
      mint_mark: r.mint_mark ?? f.mint_mark,
      grade_prefix: r.grade_prefix ?? f.grade_prefix,
      grade: r.grade ?? f.grade,
      grade_plus: r.grade ? r.grade_plus : f.grade_plus,
      grade_star: r.grade ? r.grade_star : f.grade_star,
      strike_designation: r.strike_designation ?? f.strike_designation,
      vam: r.vam ?? f.vam,
      variety: r.variety ?? f.variety,
      pcgs_number: r.pcgs_number ?? f.pcgs_number,
      cac: r.details ? false : r.cac ?? f.cac,
      cac_sticker: r.details ? null : r.cac === null ? f.cac_sticker : r.cac_sticker,
      // The grading service's word on whether it's a Details grade.
      details: Boolean(r.details),
      details_problem: r.details ? r.details_problem ?? f.details_problem : null,
      ...(r.details ? { grade_plus: false, grade_star: false } : {}),
    }));
    setImportUrls(r.image_urls);
  }

  /** Read the slab label from a photo, fill in the form, and keep the photo for the coin. */
  async function readLabel(file: File) {
    setLabelBusy(true);
    setLabelError(null);
    setLabel(null);
    try {
      const r = await api.readLabel(file);
      setLabel(r);
      if (!r.found_label) return;
      applyReading(r);
      if (!editInv) setFiles((cur) => (cur.length + importUrls.length < 10 ? [...cur, file] : cur));
      // PCGS certs can be looked up for the rest (PCGS number, photos, price guide).
      // A scanned PCGS barcode was already confirmed by a lookup, so use that one.
      if (r.lookup) {
        if (!(await checkDuplicate(r.lookup.grading_service, r.lookup.cert_number))) applyLookup(r.lookup);
      } else if (r.grading_service === "PCGS" && r.cert_number) await doLookup("PCGS", r.cert_number);
      else if (r.grading_service && r.cert_number) await checkDuplicate(r.grading_service, r.cert_number);
    } catch (e) {
      setLabelError((e as Error).message);
    } finally {
      setLabelBusy(false);
    }
  }

  function applyReading(r: LabelReading) {
      setForm((f) => ({
        ...f,
        grading_service: r.grading_service ?? (f.grading_service === "RAW" ? "PCGS" : f.grading_service),
        cert_number: r.cert_number ?? f.cert_number,
        year: r.year ?? f.year,
        mint_mark: r.mint_mark ?? f.mint_mark,
        grade_prefix: r.grade_prefix ?? f.grade_prefix,
        grade: r.grade ?? f.grade,
        grade_plus: r.grade ? r.grade_plus : f.grade_plus,
        grade_star: r.grade ? r.grade_star : f.grade_star,
        strike_designation: r.strike_designation ?? f.strike_designation,
        variety: r.variety ?? f.variety,
        vam: r.vam ?? f.vam,
        cac: r.details ? false : r.cac_sticker ? true : f.cac,
        cac_sticker: r.details ? null : r.cac_sticker ?? f.cac_sticker,
        details: r.details ?? f.details,
        details_problem: r.details ? r.details_problem ?? f.details_problem : r.details === false ? null : f.details_problem,
        ...(r.details ? { grade_plus: false, grade_star: false } : {}),
      }));
  }

  // Arrived from the "Add to TrackMyCoins" bookmark on an NGC cert page.
  useEffect(() => {
    if (!ngcHandoff) return;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    let cancelled = false;
    if (draft) {
      setForm(draft.form);
      if (draft.collectionId) setCollectionId(draft.collectionId);
      if (draft.memberTypeId) setMemberTypeId(draft.memberTypeId);
    }
    api
      .ngcPage(ngcHandoff)
      .then(async ({ reading, photos }) => {
        if (cancelled) return;
        clearCoinDraft();
        applyReading(reading);
        setLabel(reading);
        setImportUrls(photos.urls);
        setNgcPreviews(photos.previews);
        const match = pickCollection(collections, coinTypes, reading.coin_type, reading.grade_prefix);
        // Keep the user's collection if it's the right series (they may have several); otherwise switch.
        const typeOf = (id: number | null | undefined) => collections.find((c) => c.id === id)?.coin_type_id;
        const current = draft?.collectionId ?? (Number(search.get("collection")) || null);
        if (match && (!current || typeOf(current) !== typeOf(match))) setCollectionId(match);
        await checkDuplicate("NGC", reading.cert_number);
      })
      .catch((e) => setLabelError(`Couldn't read NGC's page: ${(e as Error).message}`))
      .finally(() => !cancelled && setNgcState("done"));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ngcHandoff, collections.length > 0]);

  async function removeCoin() {
    if (!editInv) return;
    const label = `${form.year ?? ""}${form.mint_mark && form.mint_mark !== "P" ? `-${form.mint_mark}` : ""}`;
    if (!confirm(`Delete ${editInv}${label ? ` (${label})` : ""}? This can't be undone.`)) return;
    try {
      await api.deleteCoin(editInv);
      await refresh();
      leaving.current = true;
      navigate(collection ? collectionPath(collection) : "/dashboard");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  /** Go to NGC's page for this coin in this tab; the bookmark there brings us back with its details. */
  function openNgc() {
    if (files.length && !confirm("Photos you've attached here can't come along to NGC and back. Continue and re-add them later?")) return;
    if (!editInv) saveCoinDraft({ form, collectionId, memberTypeId });
    leaving.current = true; // the draft comes back with us
    window.location.href = ngcCertUrl(form.cert_number, form.grade);
  }

  /** NGC has no lookup we can use, but CAC's site still tells us about a sticker. */
  async function checkCac() {
    const cert = form.cert_number?.trim();
    setCacNote(null);
    if (!cert) return;
    try {
      const r = await api.lookup("NGC", cert);
      if (r.cac) {
        setForm((f) => ({ ...f, cac: true, cac_sticker: r.cac_sticker ?? f.cac_sticker ?? "green" }));
        setCacNote(`CAC: ${r.cac_sticker ? `${r.cac_sticker} sticker` : "stickered"} (from CAC's records).`);
      }
    } catch {
      // Optional; the user can tick CAC themselves.
    }
  }

  async function findPcgs() {
    if (!coinType || !form.year) {
      setFindMsg("Enter the year and mint first.");
      return;
    }
    setFindBusy(true);
    setFindMsg(null);
    setCandidates([]);
    try {
      const m = await api.catalogMatch({
        coin_type_id: coinType.id,
        year: Number(form.year),
        mint_mark: form.mint_mark,
        designation: form.strike_designation,
        finish,
        variety: form.variety,
        gsa: form.gsa_hard_pack ? "hard" : form.gsa_soft_pack ? "soft" : null,
      });
      if (m.best?.pcgs_number) {
        set("pcgs_number", m.best.pcgs_number);
        if (m.best.variety) set("variety", m.best.variety);
        setFindMsg(`Matched ${m.best.name}${m.best.variety ? ` (${m.best.variety})` : ""}`);
      } else {
        setFindMsg(m.message);
        setCandidates(m.candidates);
      }
    } catch (e) {
      setFindMsg((e as Error).message);
    } finally {
      setFindBusy(false);
    }
  }

  function pickCandidate(c: CatalogCandidate) {
    set("pcgs_number", c.pcgs_number);
    set("variety", c.variety);
    setCandidates([]);
    setFindMsg(`Picked ${c.name}${c.variety ? ` (${c.variety})` : ""}`);
  }

  // A save that met an expired session kept the form (keepExpiredDraft); put it back once, with a note.
  const [restored, setRestored] = useState(false);
  function restoreExpiredDraft(loaded: CoinFields | null) {
    const d = takeExpiredDraft(location.pathname);
    if (!d) return;
    setForm({ ...(loaded ?? EMPTY), ...d.form });
    if (d.collectionId != null) setCollectionId(d.collectionId);
    setMemberTypeId(d.memberTypeId);
    setErrorValue(d.errorValue ?? "");
    if (d.grading) setGrading(d.grading);
    setNewCollection(d.newCollection ?? null);
    setTouchedExtra(true);
    setRestored(true);
  }
  useEffect(() => {
    if (!editInv) restoreExpiredDraft(null);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** A coin picked in the search: its collection (or a new one), date, mint, variety, designation and PCGS #. */
  function pickFromCatalog(h: CatalogHit) {
    if (h.collection_id) {
      setNewCollection(null);
      setCollectionId(h.collection_id);
    } else {
      setCollectionId(null);
      const word = h.finish === "PR" ? " Proof" : h.finish === "SPR" ? " Silver Proof" : "";
      setNewCollection({ coin_type_id: h.coin_type_id, finish: h.finish, label: `${h.series_name}${word} Collection` });
    }
    setForm((f) => ({
      ...f,
      year: h.year,
      mint_mark: h.mint_mark,
      variety: h.variety,
      strike_designation: h.designation,
      pcgs_number: h.pcgs_number,
      grade_prefix: h.finish !== "MS" ? "PR" : f.grade_prefix === "PR" ? "MS" : f.grade_prefix,
    }));
  }

  // Editing: back to the coin. Adding: to the collection it was going in (or the dashboard). Unsaved changes ask first.
  function cancel() {
    if (editInv) return navigate(coinPath(editInv));
    navigate(collection ? collectionPath(collection) : "/dashboard");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting.current) return; // a double tap must not create the coin twice
    setError(null);
    if (!collectionId && !newCollection) {
      setError("Choose a collection (create one from the sidebar first).");
      return;
    }
    if (isTypeSet && !memberTypeId) {
      setError("Choose which series this coin is from.");
      return;
    }
    const paid = parseMoney(form.price_paid);
    const sold = parseMoney(form.sale_price);
    const atPurchase = parseMoney(form.purchase_value_custom);
    const asking = parseMoney(form.asking_price);
    if ("error" in paid || "error" in sold || "error" in atPurchase || "error" in asking) {
      setError(
        [
          "error" in paid && `Price paid ${paid.error}.`,
          "error" in asking && `Asking price ${asking.error}.`,
          "error" in sold && `Sale price ${sold.error}.`,
          "error" in atPurchase && `Est. value at purchase ${atPurchase.error}.`,
        ]
          .filter(Boolean)
          .join(" "),
      );
      return;
    }
    if (form.location === "grading") {
      if (!grading.submission) {
        setError("Choose the submission this coin is going in, or start a new one.");
        return;
      }
      if (sold.value !== null || form.sale_date) {
        setError("A coin at grading can't be sold. Mark it In Inventory once it's back.");
        return;
      }
    }
    const errValue = parseMoney(errorValue);
    if (form.is_error) {
      if (!form.error_description) {
        setError("Describe the error, e.g. Off-center 20%, Double struck.");
        return;
      }
      if ("error" in errValue) {
        setError(`Estimated value ${errValue.error}.`);
        return;
      }
    }
    const declared = parseMoney(grading.declared);
    if (form.location === "grading" && "error" in declared) {
      setError(`Declared value ${declared.error}.`);
      return;
    }
    if (form.details && form.details_pct != null && (form.details_pct < 1 || form.details_pct > 100)) {
      setError("The Details % of straight CPG must be between 1 and 100.");
      return;
    }
    submitting.current = true;
    setSaving(true);
    const body = {
      ...form,
      price_paid: paid.value,
      purchase_value_custom: atPurchase.value,
      asking_price: asking.value,
      sale_price: sold.value,
      collection_id: collectionId ?? 0,
      error_value: form.is_error && "value" in errValue ? errValue.value : null,
      new_collection: !collectionId && newCollection ? { coin_type_id: newCollection.coin_type_id, finish: newCollection.finish } : undefined,
      coin_type_id: isTypeSet ? memberTypeId : undefined,
      year: form.year ? Number(form.year) : null,
      grade: form.grade ? Number(form.grade) : null,
      grading:
        form.location === "grading"
          ? {
              submission_id: grading.submission === "new" ? null : Number(grading.submission),
              new_company: grading.submission === "new" ? grading.company : null,
              expected_grade: grading.expected || null,
              declared_value: "value" in declared ? declared.value : null,
            }
          : null,
    };
    try {
      let coin = editInv
        ? await api.updateCoin(editInv, body)
        : await api.createCoin({ ...body, lookup_raw: lookup?.raw ?? undefined });
      const room = 10 - coin.photos.length;
      if (importUrls.length && room > 0) {
        try {
          coin = await api.importPhotos(coin.inventory_number, importUrls.slice(0, room));
        } catch (err) {
          alert(`Coin saved, but grading-service photos couldn't be imported: ${(err as Error).message}`);
        }
      }
      if (files.length) {
        try {
          coin = await api.uploadPhotos(coin.inventory_number, files.slice(0, 10 - coin.photos.length));
        } catch (err) {
          alert(`Coin saved, but photo upload failed: ${(err as Error).message}`);
        }
      }
      await refresh();
      leaving.current = true;
      navigate(coinPath(coin.inventory_number));
    } catch (err) {
      if (err instanceof ApiError && err.duplicate) {
        setDup({ service: form.grading_service, cert: form.cert_number ?? "", duplicate: err.duplicate });
      } else if (err instanceof ApiError && err.status === 401) {
        // Signed out while saving: keep what was entered, to put back after signing in again.
        keepExpiredDraft(location.pathname, { form, collectionId, memberTypeId, errorValue, grading, newCollection });
      } else {
        setError((err as Error).message);
      }
      submitting.current = false;
      setSaving(false);
    }
  }

  if (loading || !loaded) return <div className="page muted">Loading…</div>;
  // The coin couldn't be loaded: say so, rather than offering an empty form that would save over it.
  if (editInv && !inventoryNumber && error) return <div className="page error">{error}</div>;
  if (loadError && !collections.length) return <div className="page error">Couldn't load your collections: {loadError}</div>;
  if (!collections.length)
    return (
      <div className="page">
        <h1>Add Coin</h1>
        <div className="card empty-state">
          <p>Create a collection first, then add coins to it.</p>
          <Link className="btn btn-primary" to="/dashboard">
            Go to dashboard
          </Link>
        </div>
      </div>
    );

  const canLookUp = form.grading_service === "PCGS";
  const isNgc = form.grading_service === "NGC";
  // NGC and ANACS: no lookups we can automate, so cert + grade and a Verify button that's always there.
  const verifyOnly = isNgc || form.grading_service === "ANACS" || form.grading_service === "ICG";
  const vurl = lookup?.verify_url && form.grading_service !== "NGC" ? lookup.verify_url : verifyUrl(form.grading_service, form.cert_number ?? "", form.grade);
  const isSold = Boolean(form.sale_price || form.sale_date);

  return (
    <form className="page coin-form" onSubmit={submit}>
      {restored && (
        <p className="notice small">You were signed out while saving. What you'd entered is back; check it and save again.</p>
      )}
      <div className="page-head">
        <h1>{editInv ? `Edit ${inventoryNumber}` : isSetSeries ? "Add Set" : "Add Coin"}</h1>
        <div className="row">
          <button type="button" className="btn" onClick={cancel}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : isSetSeries ? "Save set" : "Save coin"}
          </button>
        </div>
      </div>
      {error && <p className="error banner">{error}</p>}
      {dup && (
        <DuplicateCertModal
          {...dup}
          onClose={() => setDup(null)}
          extraAction={
            ngcHandoff && importUrls.length
              ? {
                  label: `Add NGC's photos to ${dup.duplicate.inventory_number}`,
                  run: async () => {
                    await api.importPhotos(dup.duplicate.inventory_number, importUrls);
                    navigate(coinPath(dup.duplicate.inventory_number));
                  },
                }
              : undefined
          }
        />
      )}

      {/* ---- Lookup ---- */}
      {!isSetSeries && (
      <section className="card form-section lookup">
        <div className="section-head">
          <h2>Grading Service</h2>
          <label className="raw-toggle">
            <input type="checkbox" checked={isRaw} onChange={(e) => setRaw(e.target.checked)} /> Raw (ungraded)
          </label>
        </div>
        {isRaw ? (
          <p className="muted small">
            Not in a grading-service slab. Grade it yourself below if you like: a letter grade (AU), a letter grade
            with a number (AU55), or leave it blank.
          </p>
        ) : (
        <div className="lookup-bar">
          <label className="field">
            <span>Service</span>
            <select {...text("grading_service")}>
              {SERVICES.filter((s) => s !== "RAW").map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="field grow">
            <span>Cert number</span>
            <input
              {...text("cert_number")}
              placeholder={isNgc ? "e.g. 1234567-001" : form.grading_service === "ANACS" ? "e.g. 8016482" : form.grading_service === "ICG" ? "e.g. 1234567890" : "e.g. 12345678"}
              onBlur={async () => {
                if (!(await checkDuplicate()) && isNgc) checkCac();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (canLookUp) doLookup();
                  else if (isNgc && NGC_BOOKMARK_ENABLED) openNgc();
                }
              }}
            />
          </label>
          {verifyOnly && (
            <label className="field grade-mini">
              <span>Grade</span>
              <input
                inputMode="text"
                placeholder="MS62"
                maxLength={12}
                value={gradeText ?? (form.grade ? `${isProof ? "PR" : form.grade_prefix ?? ""}${form.grade}${form.grade_plus ? "+" : ""}${form.grade_star ? "★" : ""}` : "")}
                aria-invalid={gradeText !== null && gradeText.trim() !== "" && !parseGrade(gradeText)}
                onChange={(e) => {
                  const v = e.target.value;
                  setGradeText(v);
                  if (!v.trim()) return set("grade", null);
                  const g = parseGrade(v);
                  // Fills the Coin box's grade (and its MS/AU..., + and ★) as it's typed.
                  if (g)
                    setForm((f) => ({
                      ...f,
                      grade: g.grade,
                      grade_plus: g.plus,
                      grade_star: g.star,
                      grade_prefix: isProof ? "PR" : g.prefix ?? f.grade_prefix,
                    }));
                }}
                onBlur={() => setGradeText(null)}
              />
            </label>
          )}
          {canLookUp && (
            <button type="button" className="btn btn-primary" onClick={() => doLookup()} disabled={!form.cert_number || lookupBusy}>
              {lookupBusy ? "Looking up…" : "Look up"}
            </button>
          )}
          {isNgc ? (
            NGC_BOOKMARK_ENABLED ? (
              <button type="button" className="btn btn-primary" onClick={openNgc}>
                Open on NGC ↗
              </button>
            ) : (
              <a className="btn btn-primary" href={ngcCertUrl(form.cert_number, form.grade)} target="_blank" rel="noreferrer">
                Verify ↗
              </a>
            )
          ) : (
            vurl && (
              <a className={`btn${verifyOnly ? " btn-primary" : ""}`} href={vurl} target="_blank" rel="noreferrer">
                Verify ↗
              </a>
            )
          )}
        </div>
        )}
        {!isRaw && isNgc && !NGC_BOOKMARK_ENABLED && (
          <p className="muted small">
            NGC doesn't allow automated lookups. Use <strong>Verify ↗</strong> to open this coin on NGC, then fill in the
            date below.{!editInv && ngcPreviews.length === 0 ? " To save NGC's photos, copy one photo's address there and paste it here." : ""}
          </p>
        )}
        {!isRaw && isNgc && NGC_BOOKMARK_ENABLED && (
          <p className="muted small">
            NGC doesn't allow automated lookups. On NGC's page, click your <strong>Add to TrackMyCoins</strong> bookmark
            to come back here with the photos and details filled in.{" "}
            <Link to="/ngc-button">Set up the bookmark</Link>
            {!editInv && ngcPreviews.length === 0 && (
              <>
                {" · "}
                <button type="button" className="link-btn" onClick={() => setShowPaste((v) => !v)}>
                  {showPaste ? "Hide photo link" : "Paste a photo link instead"}
                </button>
              </>
            )}
          </p>
        )}
        {!isRaw && form.grading_service === "ANACS" && (
          <p className="muted small">
            ANACS doesn't allow automated lookups. Use <strong>Verify ↗</strong> to check the cert on ANACS's site, then
            fill in the date below.
          </p>
        )}
        {!isRaw && form.grading_service === "ICG" && (
          <p className="muted small">
            ICG doesn't allow automated lookups. Use <strong>Verify ↗</strong> to check the serial on ICG's site, or read it
            from a photo of the label, then fill in the date and grade below.
          </p>
        )}
        {!isRaw && form.grading_service === "CACG" && (
          <p className="muted small">
            CAC Grading doesn't allow automated lookups. Use Verify ↗, then fill in the date and grade below.
          </p>
        )}
        {cacNote && <p className="small muted">{cacNote}</p>}
        <div className="read-label">
          <span className="small muted">Or read it from a photo of the slab label:</span>
          <PhotoButtons
            multiple={false}
            takeLabel={labelBusy ? "Reading label…" : "Photo of label"}
            chooseLabel="Choose photo"
            disabled={labelBusy}
            onFiles={(fs) => readLabel(fs[0])}
          />
        </div>
        {ngcState === "busy" && <p className="muted small">Reading NGC's page…</p>}
        {ngcPreviews.length > 0 && (
          <div className="ngc-photos">
            <span className="small muted">NGC's photos (saved with the coin):</span>
            <div className="thumb-row">
              {ngcPreviews.map((u) => (
                <img key={u} className="ngc-thumb" src={u} alt="" />
              ))}
            </div>
          </div>
        )}
        {isNgc && (showPaste || !NGC_BOOKMARK_ENABLED) && !editInv && ngcPreviews.length === 0 && (
          <NgcPhotoLink
            expectedCert={form.cert_number}
            onFound={(r) => {
              if (!form.cert_number) set("cert_number", r.cert_number);
              setImportUrls((cur) => [...cur.filter((u) => !r.urls.includes(u)), ...r.urls]);
              setNgcPreviews(r.previews);
              setShowPaste(false);
            }}
          />
        )}
        {labelError && <p className="error small">{labelError}</p>}
        {label && <LabelSummary r={label} kept={!editInv && label.found_label} />}
        {lookupError && <p className="error">{lookupError}</p>}
        {lookup && (
          <div className="lookup-result">
            {lookup.description && <p className="strong">{lookup.description}</p>}
            {lookup.price_guide_value && (
              <p className="muted small">PCGS Price Guide: {money(lookup.price_guide_value)}</p>
            )}
            {lookup.warnings.map((w) => (
              <p key={w} className="warn small">
                {w}
              </p>
            ))}
            {lookup.image_urls.length > 0 && (
              <div className="import-photos">
                <span className="small muted">Photos from {lookup.grading_service} (checked ones are saved with the coin):</span>
                <div className="thumb-row">
                  {lookup.image_urls.map((u) => (
                    <label key={u} className="import-thumb">
                      <img src={u} alt="" />
                      <input
                        type="checkbox"
                        checked={importUrls.includes(u)}
                        onChange={(e) =>
                          setImportUrls((cur) => (e.target.checked ? [...cur, u] : cur.filter((x) => x !== u)))
                        }
                      />
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
      )}

      {/* ---- Coin ---- */}
      <section className="card form-section">
        <h2>{isSetSeries ? "Set" : "Coin"}</h2>
        {!editInv && <CoinSearch onPick={pickFromCatalog} />}
        <div className="grid-4">
          <label className="field">
            <span>Collection</span>
            <select
              value={collectionId ?? (newCollection ? "new" : "")}
              onChange={(e) => {
                if (e.target.value === "new") return;
                setNewCollection(null);
                setCollectionId(Number(e.target.value));
                setTouchedExtra(true);
              }}
            >
              {newCollection && !collectionId && <option value="new">New: {newCollection.label} (made when you save)</option>}
              {collectionGroups.map(({ type, collections: cols }) => (
                <optgroup key={type.id} label={type.plural}>
                  {cols.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.finish !== "MS" ? ` (${FINISH_LABEL[c.finish]})` : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          {isTypeSet && (
            <label className="field">
              <span>Series</span>
              <select
                value={memberTypeId ?? ""}
                onChange={(e) => setMemberTypeId(Number(e.target.value) || null)}
                disabled={Boolean(editInv)}
                required
              >
                <option value="">Choose a series…</option>
                {memberTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="field">
            <span>Year</span>
            <input type="number" min={1700} max={new Date().getFullYear() + 1} step={1} required {...text("year")} />
          </label>
          {isSetSeries && coinType ? (
            <SetPicker
              coinTypeId={coinType.id}
              year={Number(form.year) || null}
              mintMark={form.mint_mark}
              variety={form.variety}
              onPick={(o) => setForm((f) => ({ ...f, mint_mark: o.mint_mark, variety: o.variety, pcgs_number: o.pcgs_number }))}
            />
          ) : (
            <>
          <label className="field">
            <span>Mint</span>
            <select {...text("mint_mark")} required>
              {(coinType?.mint_marks ?? ["P"]).map((m) => (
                <option key={m} value={m}>
                  {m === "P" ? "P (no mint mark)" : m}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Variety / issue (optional)</span>
            <input
              {...text("variety")}
              placeholder={VARIETY_HINTS[coinType?.slug ?? ""] ?? "e.g. Type 2, 1942/1 (overdate), D/S (over-mintmark)"}
              maxLength={150}
            />
          </label>
            </>
          )}
        </div>
        {!isSetSeries && (
          <>
        <div className="grid-4">
          {coinType && VAM_SERIES.includes(coinType.slug) && (
            <label className="field">
              <span>VAM (optional)</span>
              <input {...text("vam")} placeholder="e.g. VAM-1A" />
            </label>
          )}
          <label className="field">
            <span>{isRaw ? "Grade (optional)" : form.details ? "Grade (number optional)" : "Grade"}</span>
            <div className="row tight">
              <select {...text("grade_prefix")} className="w-auto" disabled={isProof}>
                {isProof ? (
                  <option value="PR">PR</option>
                ) : (
                  <>
                    <option value="">—</option>
                    {CIRC_PREFIXES.map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </>
                )}
              </select>
              <input type="number" min={1} max={70} step={1} {...text("grade")} placeholder="65" />
            </div>
          </label>
          <label className="field">
            <span>Strike designation</span>
            <select {...text("strike_designation")}>
              <option value="">None</option>
              {designationOptions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>PCGS coin # (for pricing)</span>
            <div className="row tight">
              <input {...text("pcgs_number")} placeholder="e.g. 7226" />
              <button type="button" className="btn" onClick={findPcgs} disabled={findBusy} title="Find from date, mint and designation">
                {findBusy ? "…" : "Find"}
              </button>
            </div>
          </label>
        </div>
        <div className="checks coin-flags">
          <label>
            <input type="checkbox" disabled={isRaw || form.details} {...check("grade_plus")} /> Plus (+)
          </label>
          <label>
            <input type="checkbox" disabled={isRaw || form.details} {...check("grade_star")} /> Star (★)
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.details}
              onChange={(e) => {
                const on = e.target.checked;
                setForm((f) => ({
                  ...f,
                  details: on,
                  ...(on ? { grade_plus: false, grade_star: false, cac: false, cac_sticker: null } : { details_problem: null, details_pct: null }),
                }));
              }}
            />{" "}
            Details grade
            <span
              className="info-tip"
              tabIndex={0}
              title="A Details grade (e.g. “AU Details – Cleaned”) means the coin is genuine but has a problem. Price guides only cover problem-free coins, so it's valued at a share of the CPG for the same straight grade, never below melt."
            >
              ⓘ
            </span>
          </label>
          <label>
            <input type="checkbox" checked={form.is_error} onChange={(e) => setForm((f) => ({ ...f, is_error: e.target.checked }))} /> Error coin
            <span
              className="info-tip"
              tabIndex={0}
              title="Off-center strikes, double strikes, broadstrikes and the like aren't in the price guides (no PCGS number, CPG or auction data), so their value is the one you enter here."
            >
              ⓘ
            </span>
          </label>
        </div>
        {(form.details || form.is_error) && (
          <div className="grid-4 details-row">
          {form.details && (
            <>
              <label className="field">
                <span>Problem</span>
                <select value={form.details_problem ?? ""} onChange={(e) => set("details_problem", e.target.value || null)}>
                  <option value="">Not stated</option>
                  {Object.entries(DETAILS_PROBLEMS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Value at % of straight CPG</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  step={1}
                  value={form.details_pct ?? ""}
                  placeholder={`${user?.details_pct ?? 70} (your default)`}
                  onChange={(e) => set("details_pct", e.target.value === "" ? null : Math.round(Number(e.target.value)))}
                />
              </label>
            </>
          )}
          {form.is_error && (
            <>
              <label className="field span-2">
                <span>Describe the error</span>
                <input
                  value={form.error_description ?? ""}
                  onChange={(e) => set("error_description", e.target.value || null)}
                  placeholder="e.g. Off-center 20%, Double struck, Broadstrike"
                  maxLength={200}
                />
              </label>
              <label className="field">
                <span>Estimated value ($)</span>
                <input
                  value={errorValue}
                  onChange={(e) => {
                    setErrorValue(e.target.value);
                    setTouchedExtra(true);
                  }}
                  inputMode="decimal"
                  placeholder="0.00"
                />
              </label>
            </>
          )}
          </div>
        )}
        {form.is_error && (
          <p className="muted small">Error coins skip CPG, the PCGS price guide and auctions; the value you enter is its value.</p>
        )}
        {findMsg && <p className="small muted find-msg">{findMsg}</p>}
        {candidates.length > 0 && (
          <div className="candidates">
            {candidates.map((c) => (
              <button type="button" key={c.gsid} className="candidate" onClick={() => pickCandidate(c)} disabled={!c.pcgs_number}>
                <span className="mono">#{c.pcgs_number ?? "—"}</span>
                <span>{c.name}</span>
                {c.variety && <span className="muted">{c.variety}</span>}
              </button>
            ))}
          </div>
        )}
          </>
        )}
      </section>

      {/* ---- CAC / slab / packaging / toning ---- */}
      <div className="grid-3">
        {!isSetSeries && (
        <section className={`card form-section ${isRaw || form.details ? "not-applicable" : ""}`}>
          <h2>CAC</h2>
          <div className="checks col">
            <label>
              <input
                type="checkbox"
                disabled={isRaw || form.details}
                checked={form.cac}
                onChange={(e) => setForm((f) => ({ ...f, cac: e.target.checked, cac_sticker: e.target.checked ? f.cac_sticker ?? "green" : null }))}
              />{" "}
              CAC approved
            </label>
            {form.cac && !isRaw && (
              <div className="segmented">
                {(["green", "gold"] as const).map((s) => (
                  <button
                    type="button"
                    key={s}
                    className={`seg ${form.cac_sticker === s ? `active cac-${s}` : ""}`}
                    onClick={() => set("cac_sticker", s)}
                  >
                    {s === "green" ? "Green bean" : "Gold bean"}
                  </button>
                ))}
              </div>
            )}
            {isRaw && <p className="muted small">Not applicable to raw coins</p>}
            {!isRaw && form.details && <p className="muted small">CAC doesn't sticker Details coins</p>}
          </div>
        </section>
        )}
        <section className="card form-section">
          <h2>{isSetSeries ? "Packaging" : "Collector Slab"}</h2>
          {!isSetSeries && (
          <div className={`checks col ${isRaw ? "not-applicable" : ""}`}>
            {(
              [
                ["slab_soapbox", "Soapbox"],
                ["slab_ngc_fatty", "NGC Fatty"],
                ["slab_rattler", "Rattler"],
                ["slab_ogh", "OGH"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                <input type="checkbox" disabled={isRaw} {...check(key)} /> {label}
              </label>
            ))}
            {isRaw && <p className="muted small">Not applicable to raw coins</p>}
          </div>
          )}
          {packaging.length > 0 && (
            <>
              {!isSetSeries && <h3 className="subhead">Packaging</h3>}
              <div className="checks col">
                {packaging.map(([key, label, other]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={form[key]}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, [key]: e.target.checked, ...(other ? { [other]: false } : {}) }))
                      }
                    />{" "}
                    {label}
                  </label>
                ))}
              </div>
            </>
          )}
        </section>
        <section className="card form-section">
          <h2>Toning</h2>
          <div className="checks col">
            <label>
              <input type="checkbox" {...check("toning_obverse")} /> Obverse
            </label>
            <label>
              <input type="checkbox" {...check("toning_reverse")} /> Reverse
            </label>
            <label>
              <input type="checkbox" {...check("toning_dual")} /> Dual side
            </label>
            <label>
              <input type="checkbox" {...check("toning_rainbow")} /> Rainbow
            </label>
            <label>
              <input type="checkbox" {...check("toning_rim")} /> Rim toner
            </label>
          </div>
        </section>
      </div>

      <LocationCard
        location={form.location}
        onLocation={(l) => set("location", l)}
        pick={grading}
        onPick={(p) => {
          setGrading(p);
          setTouchedExtra(true);
        }}
        current={editInv ? currentGrading : null}
      />

      <section className="card form-section">
        <h2>Storage</h2>
        <StoragePicker
          storageId={form.storage_id}
          position={form.storage_position}
          onChange={(id, pos) => setForm((f) => ({ ...f, storage_id: id, storage_position: pos }))}
        />
        {form.location === "grading" && form.storage_id != null && (
          <p className="muted small">It keeps this spot while it's at grading, so you know where it goes back.</p>
        )}
      </section>

      {/* ---- Purchase / sale ---- */}
      <div className="grid-2">
        <section className="card form-section">
          <h2>Purchase</h2>
          <div className="grid-2">
            <label className="field">
              <span>Amount paid</span>
              <input type="text" inputMode="decimal" {...money_("price_paid")} placeholder="0.00" />
            </label>
            <label className="field">
              <span>Date purchased</span>
              <input type="date" min="1900-01-01" max={todayISO()} {...text("purchase_date")} />
            </label>
          </div>
          <label className="field">
            <span>Purchased from</span>
            <input {...text("purchased_from")} placeholder="Dealer, show, auction…" />
          </label>
          <label className="field">
            <span>Est. value at purchase (optional)</span>
            <input type="text" inputMode="decimal" {...money_("purchase_value_custom")} placeholder="Automatic" />
            <small className="muted">
              Leave blank and it's worked out: CPG if the coin was priced within 2 months of buying it, else CPG from
              TrackMyCoins' price history for that date, else the average of PCGS auction sales around then, else the
              price paid.
            </small>
          </label>
        </section>
        <section className={`card form-section ${isSold ? "sold-section" : ""}`}>
          <h2>Sale {isSold && <span className="tag sold">Sold</span>}</h2>
          {(user?.asking_price_on || form.asking_price) && !isSold && (
            <label className="field">
              <span>Asking price</span>
              <input type="text" inputMode="decimal" {...money_("asking_price")} placeholder="0.00" />
              <small className="muted">What you'd sell it for. Printed on its label if you choose.</small>
            </label>
          )}
          <div className="grid-2">
            <label className="field">
              <span>Sale price</span>
              <input type="text" inputMode="decimal" {...money_("sale_price")} placeholder="0.00" />
            </label>
            <label className="field">
              <span>Sale date</span>
              <input type="date" min={form.purchase_date || "1900-01-01"} max={todayISO()} {...text("sale_date")} />
            </label>
          </div>
          <label className="field">
            <span>Sold to</span>
            <input {...text("sold_to")} />
          </label>
          <p className="muted small">Filling in a sale moves the coin to the Sold list.</p>
        </section>
      </div>

      {/* ---- Notes / photos ---- */}
      <section className="card form-section">
        <h2>Notes</h2>
        <textarea rows={4} {...text("notes")} />
      </section>

      {!editInv && (
        <section className="card form-section">
          <h2>Photos</h2>
          <PhotoButtons
            disabled={files.length + importUrls.length >= 10}
            onFiles={(fs) => setFiles((cur) => [...cur, ...fs].slice(0, 10 - importUrls.length))}
          />
          {files.length > 0 && (
            <div className="thumb-row">
              {files.map((f, i) => (
                <FileThumb key={`${f.name}-${f.lastModified}-${i}`} file={f} onRemove={() => setFiles((cur) => cur.filter((_, j) => j !== i))} />
              ))}
            </div>
          )}
          <p className="muted small">
            Up to 10 photos per coin, including any imported from the grading service. You can add or remove photos
            later on the coin page.
          </p>
        </section>
      )}

      <div className="form-foot">
        {editInv && (
          <button type="button" className="btn danger-outline" onClick={removeCoin} disabled={saving}>
            Delete coin
          </button>
        )}
        <div className="row">
          <button type="button" className="btn" onClick={cancel}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : isSetSeries ? "Save set" : "Save coin"}
          </button>
        </div>
      </div>
    </form>
  );
}

function LabelSummary({ r, kept }: { r: LabelReading; kept: boolean }) {
  if (!r.found_label) {
    return <p className="warn small">Couldn't find a slab label in that photo.{r.notes ? ` ${r.notes}` : ""}</p>;
  }
  const date = r.year ? `${r.year}${r.mint_mark && r.mint_mark !== "P" ? `-${r.mint_mark}` : ""}` : "";
  const grade = `${r.grade_prefix ?? ""}${r.grade ?? ""}${r.grade_plus ? "+" : ""}${r.grade_star ? "★" : ""}`;
  const parts = [date, r.coin_type, r.variety, grade, r.strike_designation].filter(Boolean).join(" ");
  return (
    <div className="lookup-result">
      <p className="small">
        <strong>{r.source === "barcode" ? "Barcode scanned:" : r.source === "ngc_page" ? "From NGC's page:" : "Label read:"}</strong> {r.grading_service ?? "Unknown service"}
        {r.cert_number ? ` #${r.cert_number}` : ""}
        {parts ? ` · ${parts}` : ""}
        {r.cac_sticker ? ` · CAC ${r.cac_sticker}` : ""}
      </p>
      {r.confidence !== "high" && (
        <p className="warn small">Some of the label was hard to read. Check the cert number and grade before saving.</p>
      )}
      {r.notes && r.source === "claude" && <p className="muted small">{r.notes}</p>}
      <p className="muted small">
        {r.source === "ngc_page"
          ? "Fields below were filled in from NGC's page. Check them, pick the collection, and save."
          : r.source === "barcode" && !r.year
            ? `The barcode only holds the cert number. Use Verify ↗ to see ${r.grading_service ?? "the grading service"}'s details, then fill in the date and grade below.`
            : `Fields below were filled in from the label${kept ? ". The photo will be saved with the coin." : "."}`}
      </p>
    </div>
  );
}

function FileThumb({ file, onRemove }: { file: File; onRemove: () => void }) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return (
    <span className="file-thumb">
      <img src={url} alt={file.name} />
      <button type="button" className="icon-btn" onClick={onRemove} aria-label={`Remove ${file.name}`}>
        ✕
      </button>
    </span>
  );
}

/** The collection an NGC coin most likely belongs in, from the series named on NGC's page. */
function pickCollection(
  collections: { id: number; coin_type_id: number; finish: string }[],
  coinTypes: { id: number; name: string; is_type_set: boolean }[],
  coinType: string | null,
  gradePrefix: string | null,
): number | null {
  if (!coinType) return null;
  const words = (t: string) => t.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w.length > 2);
  const want = new Set(words(coinType));
  let best: { id: number; score: number } | null = null;
  for (const c of collections) {
    const t = coinTypes.find((x) => x.id === c.coin_type_id);
    if (!t || t.is_type_set) continue;
    const tw = words(t.name);
    let score = tw.filter((w) => want.has(w)).length / Math.max(tw.length, 1);
    if (score < 0.99) continue; // every word of the series name must appear
    if ((gradePrefix === "PR") === (c.finish !== "MS")) score += 0.5;
    if (!best || score > best.score) best = { id: c.id, score };
  }
  return best?.id ?? null;
}

/** Mint & proof sets: choose which of the year's sets this is (main set, a variation, or a specialty set). */
function SetPicker({
  coinTypeId,
  year,
  mintMark,
  variety,
  onPick,
}: {
  coinTypeId: number;
  year: number | null;
  mintMark: string;
  variety: string | null;
  onPick: (o: SetOption) => void;
}) {
  const [options, setOptions] = useState<SetOption[] | null>(null);
  useEffect(() => {
    if (!year || year < 1900) {
      setOptions(null);
      return;
    }
    let live = true;
    api
      .sets(coinTypeId, year)
      .then((o) => live && setOptions(o))
      .catch(() => live && setOptions([]));
    return () => {
      live = false;
    };
  }, [coinTypeId, year]);
  const key = (o: { mint_mark: string; variety: string | null }) => `${o.mint_mark}|${o.variety ?? ""}`;
  const current = `${mintMark}|${variety ?? ""}`;
  // A new item: start on the year's main set.
  useEffect(() => {
    if (options?.length && !options.some((o) => key(o) === current)) onPick(options.find((o) => !o.name) ?? options[0]);
  }, [options]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <label className="field grow-2">
      <span>Set</span>
      {options === null ? (
        <select disabled>
          <option>Enter the year first</option>
        </select>
      ) : options.length === 0 ? (
        <select disabled>
          <option>No sets that year</option>
        </select>
      ) : (
        <select
          value={current}
          onChange={(e) => {
            const o = options.find((x) => key(x) === e.target.value);
            if (o) onPick(o);
          }}
        >
          {options.map((o) => (
            <option key={o.gsid} value={key(o)}>
              {o.label}
              {o.extra ? " (other set)" : ""}
            </option>
          ))}
        </select>
      )}
    </label>
  );
}

type GradingPick = { submission: string; company: GradingCompany; expected: string; declared: string };

/** In Inventory, or At Grading in a Grading Tracker submission (an open one, or a new one started here). */
function LocationCard({
  location,
  onLocation,
  pick,
  onPick,
  current,
}: {
  location: "inventory" | "grading";
  onLocation: (l: "inventory" | "grading") => void;
  pick: GradingPick;
  onPick: (p: GradingPick) => void;
  current: Coin["grading"];
}) {
  const [open, setOpen] = useState<SubmissionSummary[] | null>(null);
  useEffect(() => {
    if (location !== "grading" || open) return;
    api
      .submissions()
      .then((subs) => {
        const out = subs.filter((s) => !s.date_returned);
        setOpen(out);
        if (!pick.submission) onPick({ ...pick, submission: out.length ? String(out[0].id) : "new" });
      })
      .catch(() => setOpen([]));
  }, [location]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="card form-section location-card">
      <h2>Status</h2>
      <div className="segmented" role="radiogroup" aria-label="Where the coin is">
        {(
          [
            ["inventory", "In Inventory"],
            ["grading", "At Grading"],
          ] as const
        ).map(([v, label]) => (
          <button key={v} type="button" role="radio" aria-checked={location === v} className={`seg ${location === v ? "active" : ""}`} onClick={() => onLocation(v)}>
            {label}
          </button>
        ))}
      </div>
      {location === "inventory" && current && (
        <p className="muted small">
          Back from grading: saving takes it out of submission #{current.number} without a result. To record its new grade,
          use Record results on the submission instead.
        </p>
      )}
      {location === "grading" && (
        <div className="grid-4 location-fields">
          <label className="field">
            <span>Submission</span>
            <select value={pick.submission} onChange={(e) => onPick({ ...pick, submission: e.target.value })}>
              {open === null && <option value="">Loading…</option>}
              {(open ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.number} {s.name ?? s.company_label}
                  {s.tier_name ? ` · ${s.tier_name}` : ""} · {s.coin_count} coin{s.coin_count === 1 ? "" : "s"}
                </option>
              ))}
              <option value="new">+ New submission…</option>
            </select>
          </label>
          {pick.submission === "new" && (
            <label className="field">
              <span>Grading company</span>
              <select value={pick.company} onChange={(e) => onPick({ ...pick, company: e.target.value as GradingCompany })}>
                {GRADING_COMPANIES.map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="field">
            <span>Expected grade (optional)</span>
            <input value={pick.expected} onChange={(e) => onPick({ ...pick, expected: e.target.value })} placeholder="e.g. MS65" maxLength={20} />
          </label>
          <label className="field">
            <span>Declared value (optional)</span>
            <input value={pick.declared} onChange={(e) => onPick({ ...pick, declared: e.target.value })} inputMode="decimal" placeholder="0.00" />
          </label>
        </div>
      )}
      {location === "grading" && pick.submission === "new" && (
        <p className="muted small">A new submission is started when you save; pick its tier and dates in the Grading Tracker.</p>
      )}
      {location === "grading" && current && pick.submission === String(current.id) && (
        <p className="muted small">
          In <Link to={`/grading/${current.id}`}>submission #{current.number}</Link>.
        </p>
      )}
    </section>
  );
}

// ---- Keeping a coin form across an expired session ----
const EXPIRED_KEY = (path: string) => `tmc-unsaved-coin:${path}`;
type ExpiredDraft = {
  form: CoinFields;
  collectionId: number | null;
  memberTypeId: number | null;
  errorValue: string;
  grading: GradingPick | null;
  newCollection: { coin_type_id: number; finish: Finish; label: string } | null;
};

function keepExpiredDraft(path: string, d: ExpiredDraft) {
  try {
    sessionStorage.setItem(EXPIRED_KEY(path), JSON.stringify({ ...d, savedAt: Date.now() }));
  } catch {
    // No storage: nothing to keep.
  }
}

function takeExpiredDraft(path: string): ExpiredDraft | null {
  try {
    const raw = sessionStorage.getItem(EXPIRED_KEY(path));
    sessionStorage.removeItem(EXPIRED_KEY(path));
    const d = raw ? JSON.parse(raw) : null;
    return d && Date.now() - d.savedAt < 60 * 60 * 1000 ? (d as ExpiredDraft) : null;
  } catch {
    return null;
  }
}

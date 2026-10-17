/**
 * The "Add to TrackMyCoins" bookmark. It runs in the collector's own browser on an NGC cert page they opened,
 * collects the cert (from the address), NGC's photo links and the page text, and brings the same tab back to our
 * add-coin form with them after the "#" (so nothing is sent until the form loads and the user is signed in).
 * The form restores whatever the user had typed before leaving for NGC (see saveCoinDraft).
 */
/**
 * The bookmark is on hold (kept for later refinement). While false, nothing about it is shown: no setup page,
 * no menu link, no mentions; NGC coins use Verify (prefilled) plus pasting a photo link.
 */
export const NGC_BOOKMARK_ENABLED = false;

export function ngcBookmarklet(origin: string): string {
  const code = `(function(){
var bad="Open a coin's NGC cert page first (ngccoin.com/certlookup/...), then use Add to TrackMyCoins.";
if(!/(^|\\.)ngccoin\\.com$/.test(location.hostname)){alert(bad);return;}
var m=location.pathname.match(/certlookup\\/(\\d{5,10}-\\d{3})(?:\\/([^\\/?]+))?/i);
if(!m){alert(bad);return;}
var html=document.documentElement.innerHTML.replace(/\\\\\\//g,"/");
var re=/https:\\/\\/ccg-imaging-ngc-coins-production\\.s3\\.amazonaws\\.com\\/[^"'\\s)<>]+?\\.jpe?g/g;
var imgs=[],x;while((x=re.exec(html))&&imgs.length<12){if(imgs.indexOf(x[0])<0)imgs.push(x[0]);}
var main=document.querySelector("main")||document.body;
var t=(main.innerText||"").replace(/[ \\t]+/g," ").replace(/\\n{2,}/g,"\\n").slice(0,4000);
var u="${origin}/coins/new#ngc="+encodeURIComponent(JSON.stringify({cert:m[1],grade:m[2]||null,images:imgs,text:t}));
location.href=u;
})();`;
  return "javascript:" + encodeURIComponent(code.replace(/\n/g, ""));
}

export interface NgcHandoff {
  cert: string;
  grade: string | null;
  images: string[];
  text: string;
}

/** The NGC data the bookmark put after "#ngc=", if any. */
export function readNgcHandoff(hash: string): NgcHandoff | null {
  if (!hash.startsWith("#ngc=")) return null;
  try {
    const d = JSON.parse(decodeURIComponent(hash.slice(5)));
    return typeof d?.cert === "string" ? { cert: d.cert, grade: d.grade ?? null, images: d.images ?? [], text: d.text ?? "" } : null;
  } catch {
    return null;
  }
}

const DRAFT_KEY = "coin-draft";
const DRAFT_MAX_AGE = 60 * 60 * 1000;

/** Keep the half-filled add-coin form while the user visits NGC in this tab. */
export function saveCoinDraft(draft: object) {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ ...draft, savedAt: Date.now() }));
  } catch {
    // Without storage the form just starts empty when they come back.
  }
}

export function readCoinDraft<T>(): T | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    const d = raw ? JSON.parse(raw) : null;
    return d && Date.now() - d.savedAt < DRAFT_MAX_AGE ? (d as T) : null;
  } catch {
    return null;
  }
}

export function clearCoinDraft() {
  try {
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // nothing to clear
  }
}

export function ngcCertUrl(cert?: string | null, grade?: number | null): string {
  const c = (cert ?? "").trim();
  if (!c) return "https://www.ngccoin.com/certlookup/";
  return `https://www.ngccoin.com/certlookup/${encodeURIComponent(c)}/${grade ? `${grade}/` : ""}`;
}

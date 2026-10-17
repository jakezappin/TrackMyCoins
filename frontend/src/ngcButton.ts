/**
 * The "Add to TrackMyCoins" bookmark. It runs in the collector's own browser on an NGC cert page they opened,
 * collects the cert (from the address), NGC's photo links and the page text, and opens our add-coin form with
 * them after the "#" (so nothing is sent until the form loads and the user is signed in).
 */
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
var w=window.open(u,"_blank");if(!w)location.href=u;
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

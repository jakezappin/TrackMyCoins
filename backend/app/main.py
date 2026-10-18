import html
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import check_production, get_settings
from .db import SessionLocal
from .models import Collection, CoinType
from .services import bullion as bullion_service, catalog as catalog_service, ebay, price_archive, quota
from .routers import attachments, auth, bullion, catalog, coins, collections, dashboard, grading, importer, jobs, label, metals, photos, pricing, reports, shared, storage, wants
from .series import SERIES


def seed_coin_types() -> None:
    """Create or update a coin_types row for every series in app/series.py."""
    with SessionLocal() as db:
        for sr in SERIES:
            fields = {
                "name": sr.name,
                "plural": sr.plural,
                "slug": sr.slug,
                "inventory_prefix": sr.prefix,
                "category": sr.category,
                "mint_marks": list(sr.mint_marks),
                "finishes": list(sr.finishes),
            }
            existing = db.scalar(
                select(CoinType).where((CoinType.slug == sr.slug) | (CoinType.name == sr.name))
            )
            if existing is None:
                db.add(CoinType(**fields))
            else:
                for k, v in fields.items():
                    if getattr(existing, k) != v:
                        setattr(existing, k, v)
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_production(get_settings())
    get_settings().photo_dir.mkdir(parents=True, exist_ok=True)
    seed_coin_types()
    if get_settings().seed_catalog:
        with SessionLocal() as db:
            catalog_service.seed_from_bundle(db)  # every series' Greysheet catalog, shipped with the app
    if get_settings().seed_spot_history:
        with SessionLocal() as db:
            bullion_service.seed_from_bundle(db)  # daily spot prices since 2000, shipped with the app
    price_archive.start_background()  # monthly price-data upkeep, while the server is up
    yield


app = FastAPI(title="Coin App", lifespan=lifespan)


@app.middleware("http")
async def one_address(request, call_next):
    """trackmycoins.fly.dev and www.trackmycoins.app -> trackmycoins.app (same path). Fly's health checks, which
    come in on the machine's own address, are left alone."""
    canonical = get_settings().canonical_host
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if canonical and host != canonical and (host == f"www.{canonical}" or host.endswith(".fly.dev")) \
            and request.url.path != "/api/health":
        url = f"https://{canonical}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
        # 308 keeps the method and body for anything but a plain page load.
        return RedirectResponse(url, status_code=301 if request.method in ("GET", "HEAD") else 308)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")  # no framing (clickjacking on delete / share buttons)
    # Share links carry their token in the address: don't pass it on to other sites.
    h.setdefault("Referrer-Policy", "no-referrer" if request.url.path.startswith(("/shared", "/api/shared")) else "same-origin")
    if get_settings().cookie_secure:
        h.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response

for r in (attachments, auth, bullion, catalog, collections, coins, dashboard, grading, importer, jobs, label, metals, photos, pricing, reports, shared, storage, wants):
    app.include_router(r.router)
app.include_router(reports.insurance_router)


@app.exception_handler(quota.QuotaExceeded)
async def _quota_exceeded(_request, exc: quota.QuotaExceeded):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/features")
def features():
    """Optional integrations that are switched on (so the UI can hide what isn't set up)."""
    return {"ebay": ebay.configured()}


@app.get("/api/public/stats")
def public_stats():
    """Numbers for the public landing page (no login needed)."""
    return {
        "series": len(SERIES),
        "collection_types": sum(len(s.finishes) for s in SERIES),
        "categories": len({s.category for s in SERIES}),
    }


# In production the built React app is served from here too (one server, one origin).
_dist = get_settings().frontend_dist
if (_dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        file = (_dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(_dist.resolve()):
            return FileResponse(file)
        if path.startswith("shared/"):
            return _shared_page(path.split("/", 1)[1])
        # Client-side routes (/coins/MOR-00005, /collections/...) all load the app.
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})

    def _shared_page(token: str):
        """The app page, titled with the collection's name, so a shared link unfurls as more than "TrackMyCoins"
        in messages and social posts."""
        page = (_dist / "index.html").read_text()
        with SessionLocal() as db:
            col = db.scalar(select(Collection).where(Collection.share_token == token.strip("/"))) if token else None
            if col is not None:
                title = html.escape(f"{col.name} · TrackMyCoins")
                desc = html.escape(f"A {col.coin_type.name} collection shared from TrackMyCoins.")
                tags = (f'<title>{title}</title>\n    <meta property="og:title" content="{title}" />\n'
                        f'    <meta property="og:description" content="{desc}" />\n'
                        f'    <meta property="og:type" content="website" />\n'
                        f'    <meta name="twitter:card" content="summary" />')
                page = re.sub(r"<title>.*?</title>", lambda _m: tags, page, count=1)
                page = re.sub(r'<meta name="description" content="[^"]*" />',
                              lambda _m: f'<meta name="description" content="{desc}" />', page, count=1)
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

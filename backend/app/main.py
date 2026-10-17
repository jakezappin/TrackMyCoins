from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import CoinType
from .routers import auth, catalog, coins, collections, dashboard, jobs, label, photos, pricing, reports, shared
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
    get_settings().photo_dir.mkdir(parents=True, exist_ok=True)
    seed_coin_types()
    yield


app = FastAPI(title="Coin App", lifespan=lifespan)
for r in (auth, catalog, collections, coins, dashboard, jobs, label, photos, pricing, reports, shared):
    app.include_router(r.router)
app.include_router(reports.insurance_router)


@app.get("/api/health")
def health():
    return {"ok": True}


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
        # Client-side routes (/coins/MOR-00005, /collections/...) all load the app.
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})

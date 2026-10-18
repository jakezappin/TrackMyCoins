"""Download every supported series' Greysheet catalog into a scratch database and write it to
app/catalog_bundle.json.gz, which ships with the app (so the coin search and Find never wait on Greysheet).
One Greysheet call per catalog section (about 150 in all); run it again when new issues come out.

    python -m scripts.build_catalog [--db sqlite:///path/to/scratch.db]
"""

import os
import sys
import time

if "--db" in sys.argv:
    os.environ["DATABASE_URL"] = sys.argv[sys.argv.index("--db") + 1]

from sqlalchemy import select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import seed_coin_types  # noqa: E402
from app.models import CoinType  # noqa: E402
from app.series import BY_SLUG  # noqa: E402
from app.services import catalog  # noqa: E402

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    seed_coin_types()
    failed = []
    with SessionLocal() as db:
        types = [t for t in db.scalars(select(CoinType).order_by(CoinType.slug))
                 if BY_SLUG.get(t.slug) and not BY_SLUG[t.slug].is_type_set]
        for i, t in enumerate(types, 1):
            try:
                r = catalog.sync(db, t)
                print(f"[{i}/{len(types)}] {t.slug}: {r.count} entries", flush=True)
            except Exception as e:  # keep going; report at the end
                db.rollback()
                failed.append(t.slug)
                print(f"[{i}/{len(types)}] {t.slug}: FAILED ({e.__class__.__name__}: {e})", flush=True)
            time.sleep(1)
        n = catalog.export_bundle(db)
    print(f"Wrote {n} entries to {catalog.BUNDLE}" + (f"; failed: {', '.join(failed)}" if failed else ""))

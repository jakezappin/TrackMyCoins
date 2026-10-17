"""Rebuild app/series_issues.json: every date and mint each series was struck at, from Greysheet's catalog.

Usage (syncs every series' catalog into DATABASE_URL first, about 110 Greysheet calls):
    DATABASE_URL=sqlite:////tmp/catalog.db python -m scripts.build_issues

Import uses the file to refuse dates that don't exist (a 1904-CC Morgan, a business-strike 1895 Morgan).
"""

import json
from collections import defaultdict
from pathlib import Path

from app.db import SessionLocal
from app.models import CatalogEntry, CoinType
from app.series import BY_SLUG
from app.services import catalog

OUT = Path(__file__).resolve().parents[1] / "app" / "series_issues.json"
STRIKE = {"MS": "MS", "SP": "MS", "SMS": "MS", "PR": "PR", "BM PR": "PR"}  # specimens/SMS count as business


def main() -> None:
    db = SessionLocal()
    types = [t for t in db.query(CoinType) if t.slug in BY_SLUG and not BY_SLUG[t.slug].is_type_set]
    for t in types:
        catalog.sync(db, t)
    db.commit()
    out: dict = {}
    for t in sorted(types, key=lambda t: t.slug):
        years: dict = defaultdict(lambda: defaultdict(set))
        for e in db.query(CatalogEntry).filter(CatalogEntry.coin_type_id == t.id, CatalogEntry.year.isnot(None)):
            years[str(e.year)][STRIKE.get(e.strike, "MS")].add(e.mint_mark or "P")
        out[t.slug] = {y: {k: " ".join(sorted(v)) for k, v in sorted(s.items())} for y, s in sorted(years.items())}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"Wrote {OUT} ({sum(len(v) for v in out.values())} dates in {len(out)} series)")


if __name__ == "__main__":
    main()

"""Check Greysheet credentials and what the catalog returns for each series.

Run from backend/:
    .venv/bin/python -m scripts.greysheet_check                        # every series (one line each)
    .venv/bin/python -m scripts.greysheet_check kennedy-half-dollars   # one series, with samples
"""

import collections
import sys

import httpx

from app.series import BY_SLUG, SERIES
from app.services import greysheet
from app.services.catalog import parse_collectible


def main() -> int:
    wanted = sys.argv[1:]
    unknown = [w for w in wanted if w not in BY_SLUG]
    if unknown:
        print(f"Unknown series: {', '.join(unknown)}\nKnown: {', '.join(BY_SLUG)}")
        return 1
    series = [BY_SLUG[w] for w in wanted] if wanted else SERIES
    detailed = bool(wanted)
    try:
        with greysheet.client() as c:
            print(f"Using {c.base_url}")
            for s in series:
                parsed = []
                for nid in dict.fromkeys([*s.ms_nodes, *s.pr_nodes]):
                    items = greysheet.get(c, "/GetCollectibleByNodeRequest", NodeId=nid)
                    parsed += [p for p in map(parse_collectible, items) if p]
                by_strike = collections.Counter(p["strike"] for p in parsed)
                desg = sorted({p["designation"] for p in parsed if p["designation"]})
                print(f"{s.plural:<32} {len(parsed):>5} coins  {dict(by_strike)}  designations: {', '.join(desg) or '—'}")
                if detailed:
                    for p in parsed[:12]:
                        print(
                            f"    pcgs={p['pcgs_number'] or '—':<7} {p['year']}-{p['mint_mark']:<2} {p['strike']} "
                            f"{p['designation'] or '':<8} {p['variety'] or '':<28} | {p['name']}"
                        )
    except (greysheet.PricingError, httpx.HTTPError) as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

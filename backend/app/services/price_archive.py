"""TrackMyCoins' own price archive: PCGS auction sales and PCGS Price Guide values, kept for good.

Everything here is data the app fetches anyway (price refreshes, the PCGS market card, value at purchase), saved
instead of thrown away. PCGS only returns about 3 years of auction sales, so the archive keeps what it drops.
CPG history lives in CpgHistory (see grade_prices.record_history).

`run_due` is the monthly upkeep, run in the background while the server is up (the Fly machine sleeps when
idle, so a fixed-time schedule wouldn't fire). For coins people hold it refreshes, within its own small daily
allowances and picking up where it left off:
- each issue's CPG price sheet once a month (adds to the CPG history), and
- each issue and grade's full auction list every 3 months (PCGS keeps 3 years, so nothing is missed).
"""

import hashlib
import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import AuctionFetch, AuctionSale, Coin, CpgHistory, GradePriceSheet, PcgsGuideHistory
from . import bullion, grade_prices, greysheet, quota
from .coins import CPG, latest_quote, on_hand
from .lookups import pcgs

log = logging.getLogger(__name__)

AUCTIONS_EVERY = timedelta(days=90)
SHEETS_EVERY = timedelta(days=30)
PAUSE_SECONDS = 1.0


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---- Auction sales ----------------------------------------------------------------------------------------------

def _fingerprint(pcgs_number: str, grade: int, plus: bool, s: dict) -> str:
    parts = [pcgs_number, str(grade), str(int(plus)), s.get("date") or "", str(Decimal(str(s["price"])).normalize()),
             str(s.get("cert_number") or ""), str(s.get("lot") or ""), str(s.get("auctioneer") or "")]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def save_sales(db: Session, pcgs_number: str, grade: int, plus: bool, sales: list[dict]) -> int:
    """Store sales not seen before (shape of pcgs.market()'s "auctions"). Returns how many were new."""
    pcgs_number = str(pcgs_number)
    rows = {}
    for s in sales:
        if not s.get("date") or s.get("price") in (None, ""):
            continue
        try:
            price = Decimal(str(s["price"]))
        except Exception:
            continue
        if price <= 0:
            continue
        fp = _fingerprint(pcgs_number, grade, plus, s)
        rows[fp] = AuctionSale(
            fingerprint=fp, pcgs_number=pcgs_number, grade=int(grade), plus=bool(plus), sale_month=s["date"],
            price=price, service=(s.get("service") or None), cac=bool(s.get("cac")),
            auctioneer=(s.get("auctioneer") or None), lot=(str(s["lot"])[:40] if s.get("lot") else None),
            cert_number=(str(s["cert_number"])[:30] if s.get("cert_number") else None),
            url=(s.get("url") or None),
        )
    if not rows:
        return 0
    have = set(db.scalars(select(AuctionSale.fingerprint).where(AuctionSale.fingerprint.in_(list(rows)))))
    new = [r for fp, r in rows.items() if fp not in have]
    db.add_all(new)
    return len(new)


def sales_for(db: Session, pcgs_number: str, grade: int, plus: bool, cac: bool | None = None) -> list[tuple[str, Decimal]]:
    """[(month, price)] of archived sales of this issue and grade: all of them, or only CAC (cac=True) or only
    plain (cac=False) ones, since a CAC sticker adds to the price."""
    q = select(AuctionSale.sale_month, AuctionSale.price).where(
        AuctionSale.pcgs_number == str(pcgs_number), AuctionSale.grade == int(grade), AuctionSale.plus == bool(plus))
    if cac is not None:
        q = q.where(AuctionSale.cac == cac)
    return [(m, p) for m, p in db.execute(q)]


def last_full_fetch(db: Session, pcgs_number: str, grade: int, plus: bool) -> datetime | None:
    f = db.scalar(select(AuctionFetch).where(AuctionFetch.pcgs_number == str(pcgs_number),
                                             AuctionFetch.grade == int(grade), AuctionFetch.plus == bool(plus)))
    return _aware(f.fetched_at) if f else None


def fetch_full(db: Session, pcgs_number: str, grade: int, plus: bool) -> int:
    """Every sale PCGS has for this issue and grade (about 3 years; one API call) into the archive. The caller
    charges the call to someone's allowance first."""
    params = {"PCGSNo": str(pcgs_number), "GradeNo": int(grade), "PlusGrade": "true" if plus else "false"}
    with pcgs._client() as c:
        apr = pcgs._get(c, "/coindetail/GetAPRByGrade", **params, NumberOfRecords=1000)
    sales = [pcgs.sale_from_apr(a) for a in apr.get("Auctions") or []]
    new = save_sales(db, pcgs_number, grade, plus, [s for s in sales if s])
    f = db.scalar(select(AuctionFetch).where(AuctionFetch.pcgs_number == str(pcgs_number),
                                             AuctionFetch.grade == int(grade), AuctionFetch.plus == bool(plus)))
    if f is None:
        f = AuctionFetch(pcgs_number=str(pcgs_number), grade=int(grade), plus=bool(plus))
        db.add(f)
    f.fetched_at, f.sales_seen = datetime.now(timezone.utc), len(sales)
    return new


# ---- PCGS Price Guide -------------------------------------------------------------------------------------------

def record_guide(db: Session, pcgs_number: str, grade: int, plus: bool, value: Decimal | None) -> None:
    if value is None or value <= 0:
        return
    now = datetime.now(timezone.utc)
    last = db.scalar(
        select(PcgsGuideHistory)
        .where(PcgsGuideHistory.pcgs_number == str(pcgs_number), PcgsGuideHistory.grade == int(grade),
               PcgsGuideHistory.plus == bool(plus))
        .order_by(PcgsGuideHistory.first_seen.desc())
    )
    value = Decimal(str(value)).quantize(Decimal("0.01"))
    if last is not None and last.value == value:
        last.last_seen = now
    else:
        db.add(PcgsGuideHistory(pcgs_number=str(pcgs_number), grade=int(grade), plus=bool(plus), value=value,
                                first_seen=now, last_seen=now))


def save_market(db: Session, data: dict, grade: int, plus: bool) -> None:
    """Keep what a PCGS market lookup returned: its recent auction sales and the Price Guide value."""
    num = data.get("pcgs_number")
    if not num:
        return
    save_sales(db, num, grade, plus, data.get("auctions") or [])
    guide = data.get("price_guide")
    record_guide(db, num, grade, plus, Decimal(str(guide)) if guide else None)


# ---- Monthly upkeep ---------------------------------------------------------------------------------------------

def _held(db: Session) -> list[Coin]:
    return list(db.scalars(on_hand(select(Coin).where(Coin.grade.is_not(None)))))


def run_due(max_seconds: float = 600) -> dict:
    """Do whatever upkeep is due, until done, out of today's allowance, or out of time. Safe to call often."""
    s = get_settings()
    done = {"sheets": 0, "auctions": 0, "stopped": None}
    started = time.time()
    with SessionLocal() as db:
        # Bullion: today's spot prices, and past prices when a gold-api.com key is set.
        try:
            bullion.record_live(db)
            bullion.update_history(db)
        except Exception as e:  # never let this stop the rest
            db.rollback()
            log.info("spot prices: %s", e)
        coins = _held(db)
        now = datetime.now(timezone.utc)

        # CPG price sheets, one per issue, monthly (each adds to the CPG history).
        if s.greysheet_api_key or s.greysheet_api_token:
            issues: dict[str, tuple[str | None, int | None]] = {}
            for c in coins:
                q = latest_quote(c, CPG)
                gsid = (q.raw or {}).get("gsid") if q is not None else None
                if c.pcgs_number:
                    issues.setdefault(f"pcgs:{c.pcgs_number}", (c.pcgs_number, None))
                elif gsid:
                    issues.setdefault(f"gsid:{gsid}", (None, gsid))
            fetched = {k: _aware(t) for k, t in db.execute(select(GradePriceSheet.key, GradePriceSheet.fetched_at))}
            for key, (num, gsid) in sorted(issues.items(), key=lambda kv: fetched.get(kv[0]) or datetime.min.replace(tzinfo=timezone.utc)):
                if fetched.get(key) and now - fetched[key] < SHEETS_EVERY:
                    continue
                if time.time() - started > max_seconds:
                    done["stopped"] = "time"
                    break
                try:
                    quota.spend(quota.ARCHIVE, "greysheet", limit=s.archive_greysheet_day)
                    grade_prices.save_sheet(db, greysheet.fetch_sheet(pcgs_number=num, gsid=gsid))
                    db.commit()
                    done["sheets"] += 1
                except quota.QuotaExceeded:
                    done["stopped"] = "greysheet allowance"
                    break
                except Exception as e:  # one issue failing shouldn't stop the rest
                    db.rollback()
                    log.info("price archive: sheet %s: %s", key, e)
                time.sleep(PAUSE_SECONDS)

        # Full auction lists, per issue and grade, every 3 months.
        if s.pcgs_api_token:
            keys = sorted({(str(c.pcgs_number), int(c.grade), bool(c.grade_plus)) for c in coins if c.pcgs_number})
            fetched = {(n, g, p): _aware(t) for n, g, p, t in db.execute(
                select(AuctionFetch.pcgs_number, AuctionFetch.grade, AuctionFetch.plus, AuctionFetch.fetched_at))}
            for key in sorted(keys, key=lambda k: fetched.get(k) or datetime.min.replace(tzinfo=timezone.utc)):
                if fetched.get(key) and now - fetched[key] < AUCTIONS_EVERY:
                    continue
                if time.time() - started > max_seconds:
                    done["stopped"] = "time"
                    break
                if quota.used_today(quota.SITE, "pcgs") >= s.pcgs_site_day // 2:
                    done["stopped"] = "PCGS allowance kept for people using the site"
                    break
                try:
                    quota.spend(quota.ARCHIVE, "pcgs", limit=s.archive_pcgs_day)
                    fetch_full(db, *key)
                    db.commit()
                    done["auctions"] += 1
                except quota.QuotaExceeded:
                    done["stopped"] = "PCGS allowance"
                    break
                except Exception as e:
                    db.rollback()
                    log.info("price archive: auctions %s: %s", key, e)
                time.sleep(PAUSE_SECONDS)
    return done


_lock = threading.Lock()


def start_background() -> None:
    """Check for due upkeep a minute after start-up, then hourly, while the server runs."""
    if not get_settings().background_jobs:
        return

    def loop():
        time.sleep(60)
        while True:
            if _lock.acquire(blocking=False):
                try:
                    result = run_due()
                    if result["sheets"] or result["auctions"]:
                        log.info("price archive upkeep: %s", result)
                except Exception:  # pragma: no cover - never let upkeep take the server down
                    log.exception("price archive upkeep failed")
                finally:
                    _lock.release()
            time.sleep(3600)

    threading.Thread(target=loop, name="price-archive", daemon=True).start()


# ---- Stats ------------------------------------------------------------------------------------------------------

def stats(db: Session) -> dict:
    """How much price data has been collected, and how big the database is."""
    page = db.execute(text("PRAGMA page_size")).scalar() or 0
    pages = db.execute(text("PRAGMA page_count")).scalar() or 0
    last_sheet = db.scalar(select(func.max(GradePriceSheet.fetched_at)))
    last_auctions = db.scalar(select(func.max(AuctionFetch.fetched_at)))
    oldest_sale = db.scalar(select(func.min(AuctionSale.sale_month)))
    oldest_cpg = db.scalar(select(func.min(CpgHistory.first_seen)))
    return {
        "cpg_prices": db.scalar(select(func.count()).select_from(CpgHistory)),
        "cpg_issues": db.scalar(select(func.count(func.distinct(CpgHistory.key)))),
        "cpg_since": _aware(oldest_cpg).date().isoformat() if oldest_cpg else None,
        "auction_sales": db.scalar(select(func.count()).select_from(AuctionSale)),
        "auction_issues": db.scalar(select(func.count()).select_from(AuctionFetch)),
        "auction_since": oldest_sale,
        "guide_values": db.scalar(select(func.count()).select_from(PcgsGuideHistory)),
        "database_mb": round(page * pages / (1024 * 1024), 1),
        "last_sheet_update": _aware(last_sheet).isoformat() if last_sheet else None,
        "last_auction_update": _aware(last_auctions).isoformat() if last_auctions else None,
        "as_of": date.today().isoformat(),
    }

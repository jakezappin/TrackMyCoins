"""Cert lookups, one module per grading service, behind a single `lookup()` entry point."""

import httpx

from ...schemas import LookupResult
from .. import pcgs_cache, quota
from . import cac, pcgs
from .base import LookupError, clean_cert

# NGC, ANACS and ICG put their verification pages behind bot protection (ICG's behind a reCAPTCHA), so the app
# can't fetch them. We return the verification link and the user copies the details.
VERIFY_URLS = {
    "NGC": "https://www.ngccoin.com/certlookup/{cert}/",
    "ANACS": "https://portal.anacs.com/Verify/CertVerification.aspx?cert={cert}",
    "ICG": "https://www.icgcoin.com/verification/",
}


def lookup(
    service: str, cert: str, check_cac: bool = True, user_id: int | None = None, fresh: bool = False
) -> LookupResult:
    """`user_id`: charge this user's daily PCGS allowance (a PCGS cert lookup is 2 calls). A PCGS cert is asked
    once and kept (a cert doesn't change); `fresh` asks again (e.g. PCGS may have added photos since)."""
    service = service.upper()
    cert = clean_cert(cert)
    if not cert:
        raise LookupError("Enter a cert number")

    if service == "PCGS":
        stored = None if fresh else pcgs_cache.get(pcgs_cache.cert_key(cert))
        if stored is not None:
            result = LookupResult.model_validate(stored)
        else:
            if user_id is not None:
                quota.spend(user_id, "pcgs", 2)
            result = pcgs.lookup(cert)
            pcgs_cache.put(pcgs_cache.cert_key(cert), result.model_dump(mode="json"))
    elif service in VERIFY_URLS:
        result = LookupResult(
            grading_service=service,
            cert_number=cert,
            verify_url=VERIFY_URLS[service].format(cert=cert),
            warnings=[
                f"{service} doesn't offer automated lookups. Open the verification page, "
                "then fill in year, mint and grade below."
            ],
        )
    elif service == "CACG":
        result = LookupResult(
            grading_service="CACG",
            cert_number=cert,
            verify_url=cac.LOOKUP_URL.format(cert=cert),
            warnings=["CACG automated lookup isn't available yet. Fill in the details below."],
        )
    else:
        raise LookupError(f"Unknown grading service: {service}")

    if check_cac and service in ("PCGS", "NGC"):
        try:
            sticker = cac.check_sticker(cert)
            result.cac = sticker["cac"]
            result.cac_sticker = sticker["sticker"]
            if sticker["cac"] and not sticker["sticker"]:
                result.warnings.append("CAC lists this cert but the sticker color couldn't be read. Please check it.")
        except (httpx.HTTPError, LookupError) as e:
            result.warnings.append(f"CAC check failed: {e}")
    return result


__all__ = ["lookup", "LookupError"]

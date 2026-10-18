"""eBay Marketplace Account Deletion notifications, required for production eBay keys.

eBay checks the endpoint with GET ?challenge_code=...; the reply is SHA-256(challenge code + verification token +
endpoint address) in hex. Deletion notices come as POSTs. TrackMyCoins keeps no eBay user data (listings are read
with an app token and only held in memory for a few minutes), so a notice needs no action beyond acknowledging it.
"""

import hashlib
import logging

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response

from ..config import get_settings

router = APIRouter(prefix="/api/ebay", tags=["ebay"])
log = logging.getLogger(__name__)


def challenge_response(challenge_code: str, token: str, endpoint: str) -> str:
    return hashlib.sha256((challenge_code + token + endpoint).encode()).hexdigest()


@router.get("/account-deletion")
def verify(challenge_code: str = Query(..., max_length=200)):
    s = get_settings()
    if not s.ebay_verification_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Not configured")
    return JSONResponse({"challengeResponse": challenge_response(challenge_code, s.ebay_verification_token,
                                                                 s.ebay_deletion_endpoint)})


@router.post("/account-deletion", status_code=status.HTTP_204_NO_CONTENT)
async def notified(request: Request):
    """A user deleted their eBay account. We store nothing about eBay users, so there's nothing to erase."""
    body = await request.body()
    log.info("eBay account deletion notice received (%d bytes); no eBay user data is stored", len(body))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

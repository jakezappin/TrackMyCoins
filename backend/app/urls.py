"""Small URL helpers shared by lookups and API models."""

import re


def absolute_url(url: str | None) -> str | None:
    """PCGS sends some links without a scheme ("www.pcgs.com/coinfacts/..."), which browsers treat as a path on our
    own site. Give them https://."""
    url = (url or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    return url if re.match(r"^https?://", url, re.I) else "https://" + url.lstrip("/")

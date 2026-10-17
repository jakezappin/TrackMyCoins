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
    if re.match(r"^https?://", url, re.I):
        return url
    if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) and not re.match(r"^[\w.-]+\.[a-z]{2,}(:\d+)?(/|$)", url, re.I):
        return None  # another scheme (javascript:, data:, ...): never a link
    return "https://" + url.lstrip("/")

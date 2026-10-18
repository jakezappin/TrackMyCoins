from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


DEV_SECRET = "dev-only-insecure-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'coin-app.db'}"
    photo_dir: Path = PROJECT_ROOT / "data" / "photos"

    session_secret: str = DEV_SECRET
    session_cookie: str = "coinapp_session"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days
    cookie_secure: bool = False  # set True once served over HTTPS

    # Who can create an account: "invite" (needs INVITE_CODE; the default), "open" (anyone) or "closed".
    # With "invite" and no INVITE_CODE set, nobody can register.
    signup_mode: str = "invite"
    invite_code: str = ""
    # Failed logins allowed per email (and per IP) within the window before further attempts are refused.
    signup_max_failures: int = 5  # wrong invite codes per IP per window, so the code can't be guessed
    signups_per_ip: int = 5  # new accounts per IP per window
    login_max_failures: int = 10
    login_window_seconds: int = 15 * 60

    # Built frontend (npm run build) to serve from the same server in production.
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    pcgs_api_token: str = ""
    greysheet_api_key: str = ""
    greysheet_api_token: str = ""
    greysheet_use_sandbox: bool = False
    # Daily limits on calls to paid / rate-limited services (only real outgoing calls count).
    claude_per_user_day: int = 30
    greysheet_per_user_day: int = 150
    pcgs_per_user_day: int = 100  # PCGS calls (a coin's market data is 2)
    pcgs_site_day: int = 900
    greysheet_site_day: int = 1500  # every Greysheet call the site makes in a day (users, catalogs, upkeep)
    # Monthly price-data upkeep in the background (services/price_archive.py): its own daily allowances, kept
    # small so it never crowds out people using the site. Off in tests.
    background_jobs: bool = True
    gold_api_key: str = ""
    seed_spot_history: bool = True  # load the bundled daily spot prices at start-up (off in tests)  # gold-api.com: daily spot price history for bullion (free tier: 10 calls an hour)
    archive_pcgs_day: int = 100
    archive_greysheet_day: int = 50
    pcgs_site_day_note: str = ""  # PCGS allows 1,000 a day for the whole site; keep a margin
    # Bulk "Refresh prices" runs allowed per user in any rolling 7 days (each run spends Greysheet/PCGS calls).
    refresh_limit_per_week: int = 2
    # eBay Browse API (Production keyset: App ID / Cert ID) for "For sale on eBay now".
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    # Claude (reads slab labels from photos). Without a key, "Read label" says it isn't set up.
    anthropic_api_key: str = ""
    label_model: str = "claude-opus-5-5"
    # Optional: skip catalog-tree discovery by naming the Greysheet node id(s) per coin type slug,
    # e.g. GREYSHEET_NODE_OVERRIDES='{"morgan-dollars": [1234]}'
    greysheet_node_overrides: dict[str, list[int]] = {}

    max_attachments_per_coin: int = 10
    max_attachment_bytes: int = 10 * 1024 * 1024
    max_photos_per_coin: int = 10
    max_photo_bytes: int = 15 * 1024 * 1024
    wholesale_discount: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()


def check_production(settings: "Settings") -> None:
    """Refuse to run on the internet with the development session secret (anyone could forge a login cookie)."""
    import os

    deployed = settings.cookie_secure or bool(os.environ.get("FLY_APP_NAME"))
    if deployed and (settings.session_secret == DEV_SECRET or len(settings.session_secret) < 32):
        raise RuntimeError(
            "SESSION_SECRET must be set to a long random value in production "
            "(e.g. fly secrets set SESSION_SECRET=$(openssl rand -hex 32))."
        )

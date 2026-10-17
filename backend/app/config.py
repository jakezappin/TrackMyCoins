from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'coin-app.db'}"
    photo_dir: Path = PROJECT_ROOT / "data" / "photos"

    session_secret: str = "dev-only-insecure-secret"
    session_cookie: str = "coinapp_session"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 days
    cookie_secure: bool = False  # set True once served over HTTPS

    # Who can create an account: "invite" (needs INVITE_CODE; the default), "open" (anyone) or "closed".
    # With "invite" and no INVITE_CODE set, nobody can register.
    signup_mode: str = "invite"
    invite_code: str = ""
    # Failed logins allowed per email (and per IP) within the window before further attempts are refused.
    login_max_failures: int = 10
    login_window_seconds: int = 15 * 60

    # Built frontend (npm run build) to serve from the same server in production.
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    pcgs_api_token: str = ""
    greysheet_api_key: str = ""
    greysheet_api_token: str = ""
    greysheet_use_sandbox: bool = False
    # eBay Browse API (Production keyset: App ID / Cert ID) for "For sale on eBay now".
    ebay_client_id: str = ""
    ebay_client_secret: str = ""
    # Claude (reads slab labels from photos). Without a key, "Read label" says it isn't set up.
    anthropic_api_key: str = ""
    label_model: str = "claude-opus-5-5"
    # Optional: skip catalog-tree discovery by naming the Greysheet node id(s) per coin type slug,
    # e.g. GREYSHEET_NODE_OVERRIDES='{"morgan-dollars": [1234]}'
    greysheet_node_overrides: dict[str, list[int]] = {}

    max_photos_per_coin: int = 10
    max_photo_bytes: int = 15 * 1024 * 1024
    wholesale_discount: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()

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

    pcgs_api_token: str = ""
    greysheet_api_key: str = ""
    greysheet_api_token: str = ""
    greysheet_use_sandbox: bool = False
    # Optional: skip catalog-tree discovery by naming the Greysheet node id(s) per coin type slug,
    # e.g. GREYSHEET_NODE_OVERRIDES='{"morgan-dollars": [1234]}'
    greysheet_node_overrides: dict[str, list[int]] = {}

    max_photos_per_coin: int = 10
    max_photo_bytes: int = 15 * 1024 * 1024
    wholesale_discount: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()

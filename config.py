"""Environment configuration. Fails loudly on missing required keys."""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    # The bot connects with asyncpg, not PostgREST — without this it starts and
    # then fails on the first message with an opaque connection error.
    "SUPABASE_DB_URL",
    "APIFY_TOKEN",
]


class Settings(BaseModel):
    telegram_bot_token: str
    gemini_api_key: str
    groq_api_key: str
    supabase_url: str
    supabase_service_key: str
    supabase_db_url: str
    apify_token: str

    weekly_quota_free: int = 15
    default_timezone: str = "Asia/Kolkata"


def load_settings() -> Settings:
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            f"{', '.join(missing)}. Copy .env.example to .env and fill them in."
        )
    try:
        return Settings(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            gemini_api_key=os.environ["GEMINI_API_KEY"],
            groq_api_key=os.environ["GROQ_API_KEY"],
            supabase_url=os.environ["SUPABASE_URL"],
            supabase_service_key=os.environ["SUPABASE_SERVICE_KEY"],
            supabase_db_url=os.environ["SUPABASE_DB_URL"],
            apify_token=os.environ["APIFY_TOKEN"],
        )
    except ValidationError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        raise

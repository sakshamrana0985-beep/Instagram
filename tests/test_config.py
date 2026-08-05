import os

import pytest

from config import REQUIRED_VARS, load_settings


def test_load_settings_raises_when_missing(monkeypatch):
    for var in REQUIRED_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="Missing required environment variables"):
        load_settings()


def test_load_settings_succeeds_when_present(monkeypatch):
    values = {
        "TELEGRAM_BOT_TOKEN": "t",
        "GEMINI_API_KEY": "g",
        "GROQ_API_KEY": "q",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "s",
        "APIFY_TOKEN": "a",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    settings = load_settings()
    assert settings.telegram_bot_token == "t"
    assert settings.weekly_quota_free == 15

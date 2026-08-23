"""The wizard is what a non-coder actually touches, so its string handling
gets the same treatment as the pipeline."""
import pytest

from scripts.first_run import (
    encode_db_password,
    identify,
    mask,
    normalize,
    prevalidate,
    read_env,
    write_env,
)


def test_read_env_parses_and_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# a comment\n\nTELEGRAM_BOT_TOKEN=abc123\nGEMINI_API_KEY = spaced \n")

    values = read_env(path)

    assert values["TELEGRAM_BOT_TOKEN"] == "abc123"
    assert values["GEMINI_API_KEY"] == "spaced"


def test_read_env_of_a_missing_file_is_empty(tmp_path):
    assert read_env(tmp_path / "nope.env") == {}


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / ".env"
    write_env({"TELEGRAM_BOT_TOKEN": "t", "APIFY_TOKEN": "a"}, path)

    values = read_env(path)

    assert values["TELEGRAM_BOT_TOKEN"] == "t"
    assert values["APIFY_TOKEN"] == "a"


def test_mask_never_shows_a_whole_secret():
    masked = mask("sb_secret_EXAMPLEVALUENOTREAL")

    assert "EXAMPLEVALUENOTREAL" not in masked
    assert masked.startswith("sb_s")


def test_short_values_are_fully_masked():
    assert mask("abc") == "***"


def test_encode_db_password_escapes_reserved_characters():
    dsn = "postgresql://postgres:pa@ss/wo?rd@db.x.supabase.co:5432/postgres"

    assert encode_db_password(dsn) == (
        "postgresql://postgres:pa%40ss%2Fwo%3Frd@db.x.supabase.co:5432/postgres"
    )


def test_encode_db_password_leaves_an_already_encoded_password_alone():
    dsn = "postgresql://postgres:pa%40ss%2Fwo@db.x.supabase.co:5432/postgres"

    assert encode_db_password(dsn) == dsn


def test_normalize_strips_the_placeholder_brackets_people_leave_in():
    normalized = normalize("SUPABASE_DB_URL", "postgresql://postgres:[hunter2]@db.x.supabase.co:5432/postgres")

    assert "[" not in normalized
    assert "hunter2" in normalized


def test_normalize_strips_quotes_and_whitespace():
    assert normalize("APIFY_TOKEN", '  "apify_api_abc"  ') == "apify_api_abc"


@pytest.mark.parametrize(
    "var,value",
    [
        ("SUPABASE_SERVICE_KEY", "sb_publishable_abc"),
        ("SUPABASE_DB_URL", "not-a-connection-string"),
        ("SUPABASE_URL", "wopo.supabase.co"),
        ("APIFY_TOKEN", ""),
    ],
)
def test_prevalidate_catches_bad_input_before_any_network_call(var, value):
    assert prevalidate(var, value) is not None


@pytest.mark.parametrize(
    "var,value",
    [
        ("SUPABASE_SERVICE_KEY", "sb_secret_abc"),
        ("SUPABASE_DB_URL", "postgresql://postgres:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"),
        ("SUPABASE_URL", "https://wopo.supabase.co"),
        ("APIFY_TOKEN", "apify_api_abc"),
    ],
)
def test_prevalidate_accepts_good_input(var, value):
    assert prevalidate(var, value) is None


@pytest.mark.parametrize(
    "var,value,expected_hint",
    [
        ("TELEGRAM_BOT_TOKEN", "gsk_abcdefghijklmnop", "Groq key"),
        ("GROQ_API_KEY", "https://wopo.supabase.co", "Supabase project URL"),
        ("GEMINI_API_KEY", "apify_api_abc", "Apify token"),
        ("APIFY_TOKEN", "8881269597:AAFSw0QUSWXpZ1X0RgVIxjl3okMABrn3ZF", "Telegram bot token"),
        ("SUPABASE_URL", "postgresql://postgres:pw@db.x.supabase.co:5432/postgres", "database connection"),
    ],
)
def test_a_value_pasted_at_the_wrong_question_is_named(var, value, expected_hint):
    """The paste landing one question off is the mistake that actually happens."""
    problem = prevalidate(var, value)

    assert problem is not None
    assert expected_hint in problem


@pytest.mark.parametrize(
    "var,value",
    [
        ("TELEGRAM_BOT_TOKEN", "8881269597:AAFSw0QUSWXpZ1X0RgVIxjl3okMABrn3ZF"),
        ("GROQ_API_KEY", "gsk_abcdefghijklmnop"),
        ("APIFY_TOKEN", "apify_api_abc"),
        ("GEMINI_API_KEY", "AQ.Ab8RN6IcExampleKeyValue"),
    ],
)
def test_the_right_value_at_the_right_question_passes(var, value):
    assert prevalidate(var, value) is None


def test_a_shapeless_telegram_token_is_rejected():
    assert "digits, a colon" in (prevalidate("TELEGRAM_BOT_TOKEN", "just-some-text") or "")

"""The credential mix-ups worth catching before they become an opaque error
on someone's first forwarded link."""
import pytest

from scripts.health_check import inspect_db_url, inspect_service_key

GOOD_DSN = "postgresql://postgres:hunter2@db.abcdef.supabase.co:5432/postgres"


def test_publishable_key_is_rejected_as_the_service_key():
    problem = inspect_service_key("sb_publishable_EXAMPLEKEYNOTREAL")
    assert problem is not None
    assert "secret key" in problem


def test_secret_key_passes():
    assert inspect_service_key("sb_secret_abc123") is None


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://postgres:[YOUR-PASSWORD]@db.abcdef.supabase.co:5432/postgres",
        "postgresql://postgres:[sb_publishable_abc]@db.abcdef.supabase.co:5432/postgres",
    ],
)
def test_placeholder_brackets_are_caught(dsn):
    assert "[...]" in (inspect_db_url(dsn) or "")


def test_api_key_used_as_db_password_is_caught():
    problem = inspect_db_url("postgresql://postgres:sb_publishable_abc@db.x.supabase.co:5432/postgres")
    assert problem is not None
    assert "database password" in problem


def test_missing_password_is_caught():
    assert inspect_db_url("postgresql://postgres@db.x.supabase.co:5432/postgres") is not None


def test_valid_dsn_passes():
    assert inspect_db_url(GOOD_DSN) is None


def test_pooler_dsn_passes():
    assert inspect_db_url("postgresql://postgres.abcdef:hunter2@aws-0-ap-south-1.pooler.supabase.com:5432/postgres") is None


@pytest.mark.parametrize("password,expected", [("a@b", "@ -> %40"), ("a/b", "/ -> %2F"), ("a?b", "? -> %3F")])
def test_reserved_characters_in_the_password_are_caught(password, expected):
    """Supabase generates passwords containing @ / ? — pasted raw, the DSN
    parses as a different host entirely."""
    problem = inspect_db_url(f"postgresql://postgres:{password}@db.x.supabase.co:5432/postgres")

    assert problem is not None
    assert expected in problem


def test_percent_encoded_password_passes():
    assert inspect_db_url("postgresql://postgres:pa%40ss%2Fwo%3Frd@db.x.supabase.co:5432/postgres") is None


class _TypedUser:
    """Shape newer apify-client versions return instead of a dict."""

    username = "shubham"


def test_apify_username_read_from_a_typed_response():
    from scripts.health_check import account_username

    assert account_username(_TypedUser()) == "shubham"


def test_apify_username_read_from_a_dict_response():
    from scripts.health_check import account_username

    assert account_username({"username": "shubham"}) == "shubham"


def test_apify_username_falls_back_when_absent():
    from scripts.health_check import account_username

    assert account_username(object()) == "?"
    assert account_username({}) == "?"

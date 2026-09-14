from fx2active_bot.web_server import (
    SESSION_COOKIE,
    SessionStore,
    is_private_client,
    pin_matches,
    session_token_from_cookie,
)


def test_private_client_accepts_loopback_and_private_ipv4() -> None:
    assert is_private_client("127.0.0.1") is True
    assert is_private_client("192.168.1.40") is True
    assert is_private_client("10.0.0.7") is True


def test_private_client_rejects_public_ipv4() -> None:
    assert is_private_client("8.8.8.8") is False


def test_pin_match_uses_expected_pin() -> None:
    assert pin_matches("123456", "123456") is True
    assert pin_matches("654321", "123456") is False
    assert pin_matches(None, "123456") is False
    assert pin_matches(None, None) is True


def test_session_store_creates_and_revokes_tokens() -> None:
    store = SessionStore()
    token = store.create()
    assert store.contains(token) is True
    store.revoke(token)
    assert store.contains(token) is False


def test_session_cookie_parser_reads_fx2active_token() -> None:
    assert session_token_from_cookie(f"other=x; {SESSION_COOKIE}=abc123") == "abc123"
    assert session_token_from_cookie(None) is None

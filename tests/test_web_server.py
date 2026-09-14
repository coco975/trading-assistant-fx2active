import base64

from fx2active_bot.web_server import basic_auth_matches, is_private_client


def auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def test_private_client_accepts_loopback_and_private_ipv4() -> None:
    assert is_private_client("127.0.0.1") is True
    assert is_private_client("192.168.1.40") is True
    assert is_private_client("10.0.0.7") is True


def test_private_client_rejects_public_ipv4() -> None:
    assert is_private_client("8.8.8.8") is False


def test_basic_auth_requires_expected_username_and_pin() -> None:
    pin = "123456"
    assert basic_auth_matches(auth_header("fx2active", pin), pin) is True
    assert basic_auth_matches(auth_header("fx2active", "654321"), pin) is False
    assert basic_auth_matches(auth_header("someone", pin), pin) is False
    assert basic_auth_matches(None, pin) is False


def test_basic_auth_is_disabled_when_no_pin_is_configured() -> None:
    assert basic_auth_matches(None, None) is True

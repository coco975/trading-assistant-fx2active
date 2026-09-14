from types import SimpleNamespace

from fx2active_bot.local_runtime import LocalRuntimeMonitor
from fx2active_bot.runtime_settings import RuntimeSettings


def test_pip_size_for_five_digit_fx_symbol() -> None:
    info = SimpleNamespace(point=0.00001, digits=5)
    assert LocalRuntimeMonitor._pip_size(info) == 0.0001


def test_pip_size_for_two_digit_symbol() -> None:
    info = SimpleNamespace(point=0.01, digits=2)
    assert LocalRuntimeMonitor._pip_size(info) == 0.01


def test_runtime_symbol_is_trimmed_on_load_payload() -> None:
    settings = RuntimeSettings.from_dict({"symbol": "  EURUSD.a  "})
    assert settings.symbol == "EURUSD.a"

from fx2active_bot.runtime_settings import PoiSettings, RuntimeSettings, RuntimeSettingsStore
from fx2active_bot.worker_control import WorkerControl


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    store = RuntimeSettingsStore(path)
    expected = RuntimeSettings(
        trading_enabled=True,
        allow_buys=True,
        allow_sells=True,
        max_open_positions=3,
        poi=PoiSettings(min_confirmations=2),
    )
    store.save(expected)
    assert store.load() == expected


def test_worker_blocks_when_disabled(tmp_path):
    path = tmp_path / "settings.json"
    RuntimeSettingsStore(path).save(RuntimeSettings(trading_enabled=False))
    worker = WorkerControl(path, pip_size=0.0001)
    assert worker.can_open_position(0).allowed is False


def test_worker_respects_position_cap(tmp_path):
    path = tmp_path / "settings.json"
    RuntimeSettingsStore(path).save(RuntimeSettings(trading_enabled=True, max_open_positions=2))
    worker = WorkerControl(path, pip_size=0.0001)
    assert worker.can_open_position(1).allowed is True
    assert worker.can_open_position(2).allowed is False


def test_worker_respects_direction_switches(tmp_path):
    path = tmp_path / "settings.json"
    RuntimeSettingsStore(path).save(
        RuntimeSettings(trading_enabled=True, allow_buys=False, allow_sells=True)
    )
    worker = WorkerControl(path, pip_size=0.0001)
    assert worker.can_open_position(0, side="BUY").allowed is False
    assert worker.can_open_position(0, side="SELL").allowed is True

import json

from fx2active_bot.runtime_settings import RuntimeSettingsStore


def test_tracked_config_is_template_and_runtime_file_is_mutable(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    template = config_dir / "runtime_settings.json"
    template.write_text(
        json.dumps({"symbol": "XAUUSDm", "risk_percent": 2.0}),
        encoding="utf-8",
    )

    store = RuntimeSettingsStore(template)
    settings = store.load()

    assert settings.symbol == "XAUUSDm"
    assert settings.risk_percent == 2.0
    assert store.path == tmp_path / "data" / "runtime" / "runtime_settings.json"
    assert store.path.is_file()

    updated = settings.to_dict()
    updated["risk_percent"] = 1.25
    store.save(type(settings).from_dict(updated))

    assert json.loads(template.read_text(encoding="utf-8"))["risk_percent"] == 2.0
    assert json.loads(store.path.read_text(encoding="utf-8"))["risk_percent"] == 1.25

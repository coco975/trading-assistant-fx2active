from pathlib import Path

from fx2active_bot.web_server import ControlPanelServer


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    ControlPanelServer(
        settings_path=ROOT / "config" / "runtime_settings.json",
        web_root=ROOT / "web",
        host="127.0.0.1",
        port=8080,
    ).serve_forever()

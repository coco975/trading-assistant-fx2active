import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fx2active_bot.web_server import ControlPanelServer  # noqa: E402


if __name__ == "__main__":
    ControlPanelServer(
        settings_path=ROOT / "config" / "runtime_settings.json",
        web_root=ROOT / "web",
        host="127.0.0.1",
        port=8080,
    ).serve_forever()

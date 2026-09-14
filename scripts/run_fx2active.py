from pathlib import Path

from fx2active_bot.local_runtime import run_local_system


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    run_local_system(ROOT, host="127.0.0.1", port=8080)

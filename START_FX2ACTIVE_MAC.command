#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1

printf '\n================================================\n'
printf '  FX2Active Trading Assistant - macOS Launcher\n'
printf '================================================\n\n'
printf 'Checks Python, the local environment, MT5 bridge, worker and dashboard.\n'
printf 'No public hosting or router port forwarding is used.\n\n'

PY_CMD=""

load_homebrew_path() {
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

find_python() {
  PY_CMD=""
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
        PY_CMD="$candidate"
        return 0
      fi
    fi
  done
  return 1
}

ensure_homebrew() {
  load_homebrew_path
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi

  printf '\n[MISSING] Homebrew is required only because a supported Python was not found.\n'
  read -r -p 'Install Homebrew now? [Y/n]: ' answer
  case "$answer" in
    n|N|no|NO) return 1 ;;
    *)
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || return 1
      load_homebrew_path
      command -v brew >/dev/null 2>&1 || return 1
      ;;
  esac
}

install_supported_python() {
  ensure_homebrew || return 1
  printf '\n[SETUP] Installing a supported Python runtime...\n'
  brew update || return 1
  if brew list --versions python@3.14 >/dev/null 2>&1; then
    brew upgrade python@3.14 2>/dev/null || true
  else
    brew install python@3.14 || return 1
  fi
  load_homebrew_path
  find_python
}

load_homebrew_path
find_python || true

if [ -z "$PY_CMD" ]; then
  printf '[MISSING] Python 3.11 or newer was not found.\n'
  printf 'FX2Active supports Python 3.11 through current Python releases.\n'
  read -r -p 'Install a supported Python automatically now? [Y/n]: ' answer
  case "$answer" in
    n|N|no|NO)
      printf 'Python setup cancelled. Install Python 3.11+ and run this launcher again.\n'
      read -r -p 'Press Enter to close...'
      exit 1
      ;;
    *)
      if ! install_supported_python; then
        printf '[ERROR] Python installation could not be completed.\n'
        read -r -p 'Press Enter to close...'
        exit 1
      fi
      ;;
  esac
fi

printf '[OK] Python selected: '
"$PY_CMD" --version

if [ -e ".venv/bin/python" ]; then
  if ! ".venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    printf '[REPAIR] Existing .venv is broken or uses unsupported Python. Rebuilding it...\n'
    rm -rf .venv
  fi
fi

if [ ! -x ".venv/bin/python" ]; then
  printf '[SETUP] Creating the private FX2Active Python environment...\n'
  "$PY_CMD" -m venv .venv || {
    printf '[ERROR] Failed to create .venv.\n'
    read -r -p 'Press Enter to close...'
    exit 1
  }
fi

if ! ".venv/bin/python" -m pip --version >/dev/null 2>&1; then
  printf '[REPAIR] pip is missing from .venv. Repairing it locally...\n'
  ".venv/bin/python" -m ensurepip --upgrade || {
    printf '[ERROR] Could not repair pip inside .venv.\n'
    read -r -p 'Press Enter to close...'
    exit 1
  }
fi

printf '[OK] Local Python environment is healthy.\n'

printf '%s\n' '------------------------------------------------'
printf 'Dashboard access\n'
printf '%s\n' '------------------------------------------------'
printf '[1] This Mac only\n'
printf '[2] Devices on the same private Wi-Fi / LAN\n'

while true; do
  read -r -p 'Choose 1 or 2: ' access_choice
  case "$access_choice" in
    1)
      export FX2ACTIVE_ACCESS_MODE="local"
      unset FX2ACTIVE_DASHBOARD_PIN 2>/dev/null || true
      printf '[OK] Dashboard will be available on this Mac only.\n'
      break
      ;;
    2)
      export FX2ACTIVE_ACCESS_MODE="lan"
      FX2ACTIVE_DASHBOARD_PIN="$(".venv/bin/python" -c 'import secrets; print(secrets.randbelow(900000)+100000)')"
      export FX2ACTIVE_DASHBOARD_PIN
      printf '\n[OK] Private Wi-Fi / LAN dashboard mode selected.\n'
      printf 'Temporary access PIN: %s\n' "$FX2ACTIVE_DASHBOARD_PIN"
      printf 'Enter it once on the other device for that browser session.\n'
      printf 'If macOS asks about incoming connections, choose Allow.\n'
      printf 'Do not create router port forwarding for port 8080.\n'
      break
      ;;
    *) printf 'Please choose 1 or 2.\n' ;;
  esac
done

export PYTHONUNBUFFERED=1
".venv/bin/python" scripts/bootstrap.py
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
  printf '\nFX2Active stopped with an error. Read the message above for the exact reason.\n'
  read -r -p 'Press Enter to close...'
fi
exit "$EXIT_CODE"

#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1

printf '\n================================================\n'
printf '  FX2Active Trading Assistant - macOS Launcher\n'
printf '================================================\n\n'
printf 'This launcher checks the Mac, prepares FX2Active, verifies MT5,\n'
printf 'starts the strategy worker and opens the control website.\n'
printf 'No public hosting or router port forwarding is used.\n\n'

PY_CMD=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
      PY_CMD="$candidate"
      break
    fi
  fi
done

install_python_with_brew() {
  if ! command -v brew >/dev/null 2>&1; then
    printf '[MISSING] Homebrew is not installed.\n'
    printf 'Homebrew can install the supported Python runtime for FX2Active.\n'
    read -r -p 'Install Homebrew from its official installer now? [y/N]: ' answer
    case "$answer" in
      y|Y|yes|YES)
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || return 1
        if [ -x /opt/homebrew/bin/brew ]; then
          eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -x /usr/local/bin/brew ]; then
          eval "$(/usr/local/bin/brew shellenv)"
        fi
        ;;
      *) return 1 ;;
    esac
  fi

  printf '\nPython 3.12 runs the FX2Active worker and local website.\n'
  read -r -p 'Install Python 3.12 with Homebrew now? [y/N]: ' answer
  case "$answer" in
    y|Y|yes|YES) brew install python@3.12 || return 1 ;;
    *) return 1 ;;
  esac

  if command -v python3.12 >/dev/null 2>&1; then
    PY_CMD="python3.12"
  elif [ -x /opt/homebrew/bin/python3.12 ]; then
    PY_CMD="/opt/homebrew/bin/python3.12"
  elif [ -x /usr/local/bin/python3.12 ]; then
    PY_CMD="/usr/local/bin/python3.12"
  fi
}

if [ -z "$PY_CMD" ]; then
  printf '[MISSING] Python 3.11 or newer was not found.\n'
  if ! install_python_with_brew; then
    printf '\nPython setup was not completed. You can also install Python 3.12+ from python.org,\n'
    printf 'then run START_FX2ACTIVE_MAC.command again.\n'
    read -r -p 'Press Enter to close...'
    exit 1
  fi
fi

printf '[OK] Python detected: '
"$PY_CMD" --version

if [ ! -x ".venv/bin/python" ]; then
  printf '\n[SETUP] FX2Active needs its own isolated Python environment.\n'
  printf 'This keeps its packages separate from the rest of the Mac.\n'
  read -r -p 'Create the local .venv environment now? [y/N]: ' answer
  case "$answer" in
    y|Y|yes|YES)
      "$PY_CMD" -m venv .venv || {
        printf 'Failed to create the Python environment.\n'
        read -r -p 'Press Enter to close...'
        exit 1
      }
      ;;
    *)
      printf 'Setup cancelled. Nothing was installed.\n'
      read -r -p 'Press Enter to close...'
      exit 1
      ;;
  esac
fi

printf '\n------------------------------------------------\n'
printf 'Dashboard access\n'
printf '------------------------------------------------\n'
printf '[1] This Mac only\n'
printf '[2] Devices on the same private Wi-Fi / LAN\n'
read -r -p 'Choose 1 or 2: ' access_choice

if [ "$access_choice" = "2" ]; then
  export FX2ACTIVE_ACCESS_MODE="lan"
  FX2ACTIVE_DASHBOARD_PIN="$("$PY_CMD" -c 'import secrets; print(secrets.randbelow(900000)+100000)')"
  export FX2ACTIVE_DASHBOARD_PIN
  printf '\n[OK] Private Wi-Fi / LAN dashboard mode selected.\n'
  printf 'Temporary access PIN: %s\n' "$FX2ACTIVE_DASHBOARD_PIN"
  printf 'Enter this PIN once on the other device; it stays signed in for that browser session.\n'
  printf 'If macOS asks whether Python can accept incoming connections, choose Allow.\n'
  printf 'Do not create router port forwarding for port 8080.\n'
else
  export FX2ACTIVE_ACCESS_MODE="local"
  unset FX2ACTIVE_DASHBOARD_PIN 2>/dev/null || true
  printf '[OK] Dashboard will be available on this Mac only.\n'
fi

".venv/bin/python" scripts/bootstrap.py
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
  printf '\nFX2Active stopped with an error. Read the message above for the exact reason.\n'
  read -r -p 'Press Enter to close...'
fi
exit "$EXIT_CODE"

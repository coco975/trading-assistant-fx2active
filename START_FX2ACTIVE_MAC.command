#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1

printf '\n================================================\n'
printf '  FX2Active Trading Assistant - macOS Launcher\n'
printf '================================================\n\n'
printf 'This launcher checks the Mac, prepares FX2Active, verifies MT5,\n'
printf 'starts the strategy worker and opens the control website.\n'
printf 'No public hosting or router port forwarding is used.\n\n'

# FX2Active requires Python 3.11+. Python 3.14 is the current recommended
# macOS runtime for new installs. Older supported versions can still be used
# if the user chooses not to update.
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11
RECOMMENDED_PYTHON_MAJOR=3
RECOMMENDED_PYTHON_MINOR=14
PY_CMD=""
PYTHON_UPDATED=0

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

python_is_recommended() {
  [ -n "$PY_CMD" ] || return 1
  "$PY_CMD" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,14) else 1)' >/dev/null 2>&1
}

ensure_homebrew() {
  load_homebrew_path
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi

  printf '\n[MISSING] Homebrew is not installed.\n'
  printf 'Homebrew is used to install/update Python safely on this Mac.\n'
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

install_or_update_python() {
  ensure_homebrew || return 1

  printf '\n[SETUP] Checking Homebrew for the recommended Python 3.14 runtime...\n'
  brew update || return 1

  if brew list --versions python@3.14 >/dev/null 2>&1; then
    if brew outdated python@3.14 2>/dev/null | grep -q .; then
      printf '[UPDATE] A newer Python 3.14 build is available. Updating now...\n'
      brew upgrade python@3.14 || return 1
    else
      printf '[OK] Homebrew Python 3.14 is already up to date.\n'
    fi
  else
    printf '[INSTALL] Installing Python 3.14...\n'
    brew install python@3.14 || return 1
  fi

  load_homebrew_path

  if command -v python3.14 >/dev/null 2>&1; then
    PY_CMD="python3.14"
  elif [ -x /opt/homebrew/bin/python3.14 ]; then
    PY_CMD="/opt/homebrew/bin/python3.14"
  elif [ -x /usr/local/bin/python3.14 ]; then
    PY_CMD="/usr/local/bin/python3.14"
  else
    prefix="$(brew --prefix python@3.14 2>/dev/null || true)"
    if [ -n "$prefix" ] && [ -x "$prefix/bin/python3.14" ]; then
      PY_CMD="$prefix/bin/python3.14"
    else
      return 1
    fi
  fi

  PYTHON_UPDATED=1
  return 0
}

load_homebrew_path
find_python || true

if [ -z "$PY_CMD" ]; then
  printf '[MISSING] Python 3.11 or newer was not found.\n'
  printf 'FX2Active needs Python to run the bot, diagnostics and dashboard.\n'
  read -r -p 'Install the recommended Python 3.14 now? [Y/n]: ' answer
  case "$answer" in
    n|N|no|NO)
      printf '\nPython setup was cancelled. Install Python 3.11+ and run this launcher again.\n'
      read -r -p 'Press Enter to close...'
      exit 1
      ;;
    *)
      if ! install_or_update_python; then
        printf '\nPython installation could not be completed.\n'
        printf 'Install Python 3.14 manually, then run START_FX2ACTIVE_MAC.command again.\n'
        read -r -p 'Press Enter to close...'
        exit 1
      fi
      ;;
  esac
else
  printf '[OK] Python detected: '
  "$PY_CMD" --version

  if ! python_is_recommended; then
    printf '[UPDATE] FX2Active recommends Python 3.14 for new macOS installs.\n'
    read -r -p 'Update Python to 3.14 now? [Y/n]: ' answer
    case "$answer" in
      n|N|no|NO)
        printf '[OK] Keeping the installed supported Python version.\n'
        ;;
      *)
        if ! install_or_update_python; then
          printf '[WARN] Python update was not completed. Continuing with the existing supported version.\n'
          find_python || true
        fi
        ;;
    esac
  elif command -v brew >/dev/null 2>&1 && brew list --versions python@3.14 >/dev/null 2>&1; then
    if brew outdated python@3.14 2>/dev/null | grep -q .; then
      printf '[UPDATE] A newer Python 3.14 maintenance update is available.\n'
      read -r -p 'Install the Python update now? [Y/n]: ' answer
      case "$answer" in
        n|N|no|NO) printf '[OK] Python update skipped.\n' ;;
        *)
          if install_or_update_python; then
            printf '[OK] Python updated successfully.\n'
          else
            printf '[WARN] Python update failed. Continuing with the current supported version.\n'
            find_python || true
          fi
          ;;
      esac
    fi
  fi
fi

if [ -z "$PY_CMD" ]; then
  printf '[ERROR] No supported Python runtime is available.\n'
  read -r -p 'Press Enter to close...'
  exit 1
fi

printf '[OK] Python selected: '
"$PY_CMD" --version

# If Python was upgraded, rebuild an older virtual environment so FX2Active
# actually uses the new interpreter instead of continuing to run the old one.
if [ -x ".venv/bin/python" ]; then
  if ! ".venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    printf '\n[UPDATE] The existing FX2Active .venv uses an unsupported Python version.\n'
    printf 'Rebuilding the local environment is required.\n'
    rm -rf .venv
  elif [ "$PYTHON_UPDATED" -eq 1 ] && ! ".venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,14) else 1)' >/dev/null 2>&1; then
    printf '\n[UPDATE] Rebuilding the FX2Active .venv to use the new Python version...\n'
    rm -rf .venv
  fi
fi

if [ ! -x ".venv/bin/python" ]; then
  printf '\n[SETUP] FX2Active needs its own isolated Python environment.\n'
  printf 'This keeps its packages separate from the rest of the Mac.\n'
  read -r -p 'Create the local .venv environment now? [Y/n]: ' answer
  case "$answer" in
    n|N|no|NO)
      printf 'Setup cancelled. Nothing else was installed.\n'
      read -r -p 'Press Enter to close...'
      exit 1
      ;;
    *)
      "$PY_CMD" -m venv .venv || {
        printf 'Failed to create the Python environment.\n'
        read -r -p 'Press Enter to close...'
        exit 1
      }
      ;;
  esac
fi

printf '\n[SETUP] Checking pip inside the FX2Active environment...\n'
".venv/bin/python" -m pip install --upgrade pip setuptools wheel || {
  printf '[ERROR] Could not prepare pip inside the FX2Active environment.\n'
  read -r -p 'Press Enter to close...'
  exit 1
}

printf '\n------------------------------------------------\n'
printf 'Dashboard access\n'
printf '------------------------------------------------\n'
printf '[1] This Mac only\n'
printf '[2] Devices on the same private Wi-Fi / LAN\n'
read -r -p 'Choose 1 or 2: ' access_choice

if [ "$access_choice" = "2" ]; then
  export FX2ACTIVE_ACCESS_MODE="lan"
  FX2ACTIVE_DASHBOARD_PIN="$(".venv/bin/python" -c 'import secrets; print(secrets.randbelow(900000)+100000)')"
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

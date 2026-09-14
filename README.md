# Trading Assistant for FX2Active

A Windows-local M15 Fibonacci trading assistant with a simple browser control panel. No Vercel, Cloudflare Tunnel, public URL, web-control key, or remote settings service is required for this build.

## Normal use: one launcher

The person running the bot should not need to work from PowerShell or remember several commands.

On Windows, double-click:

```text
START_FX2ACTIVE.bat
```

That launcher is responsible for the startup flow:

```text
START_FX2ACTIVE.bat
        ↓
Check Python
        ↓
Create isolated .venv if needed
        ↓
Explain missing Python dependencies
        ↓
Ask permission before installing them
        ↓
Run system diagnosis
        ↓
Verify MT5 terminal + account connection
        ↓
Verify local web port + strategy settings
        ↓
Start local worker/health monitor
        ↓
Start localhost dashboard
        ↓
Open browser automatically
```

The control panel is available only on the PC at:

```text
http://127.0.0.1:8080
```

Keep the launcher window open while the local bot system is running. `Ctrl+C` stops it.

## What can be installed automatically?

The launcher never silently installs software.

If something is missing, it explains what it is and asks `Y/N` first.

### Python

Python runs the strategy, system checks, MT5 bridge, and local web server. If Python is completely missing, the Windows launcher can offer to install Python 3.12 through Windows Package Manager (`winget`).

### Local `.venv`

The bot creates an isolated `.venv` folder so its Python packages do not interfere with the rest of the PC. The launcher asks before creating it.

### MetaTrader5 Python package

`MetaTrader5` is the Python bridge used to read MT5 terminal/account state, positions, and later the trading data/execution interface. It is installed only inside this bot's `.venv`, and the bootstrap explains it before requesting permission.

### MetaTrader 5 desktop terminal

The launcher does **not** silently install an MT5 desktop terminal. Different brokers can provide different branded MT5 terminals, so guessing a terminal would be unsafe. The system diagnosis instead verifies that a compatible MT5 terminal is installed, connected, and logged into the intended account.

The bot does not store the MT5 password in GitHub or return it through the dashboard. Account readiness is checked from the active MT5 terminal session, and the dashboard only shows a masked account number plus the server.

## System diagnosis

Before startup the bot checks:

- Python version
- Windows runtime
- validated strategy settings
- localhost port availability
- MetaTrader5 Python bridge
- MT5 terminal connection
- logged-in MT5 account
- trading permission reported by MT5

The dashboard also has a **Run system check** button so the user can repeat the checks without using the command prompt.

The top status bar shows, in plain language:

- Worker online/offline
- MT5 connected/not connected
- Account connected/not connected
- Open positions versus the configured maximum

## Web-controlled strategy

Pressing **Done — Apply to Bot** writes the validated settings to `config/runtime_settings.json`. The strategy layer reloads those settings during evaluation, so a toggle change affects the worker without rebuilding or restarting the bot.

The dashboard controls:

- Master trading enabled / disabled
- BUY enabled / disabled
- SELL enabled / disabled
- Fibonacci rule enabled / disabled
- Fib retracement value, default `0.786`
- Stop-loss buffer in pips, default `10`
- Take-profit mode: opposite swing target
- Entry trigger
- Maximum open positions
- Support / resistance confirmation
- Previous swing confirmation
- Trendline confirmation
- Psychological level confirmation
- Candle confirmation
- Minimum number of POI confirmations required

## Core strategy

- Timeframe: M15
- Directions: BUY and SELL
- BUY Fibonacci placement: Swing Low -> Swing High
- SELL Fibonacci placement: Swing High -> Swing Low
- Default Fib entry: 78.6% retracement
- BUY stop loss: 10 configurable pips below the 100% Fib / Swing Low
- SELL stop loss: 10 configurable pips above the 100% Fib / Swing High
- BUY take profit: Swing High / 0% Fib
- SELL take profit: Swing Low / 0% Fib

### BUY

```text
Bullish impulse
Swing Low -> Swing High
        ↓
78.6% retracement
        ↓
BUY setup
SL = 10 pips below Swing Low / 100%
TP = Swing High / 0%
```

### SELL

```text
Bearish impulse
Swing High -> Swing Low
        ↓
78.6% retracement
        ↓
SELL setup
SL = 10 pips above Swing High / 100%
TP = Swing Low / 0%
```

## POI implementation

The current POI code turns common price-action/confluence concepts into deterministic test heuristics. These are engineering definitions for this bot, not proprietary BabyPips algorithms.

- Support/resistance: repeated horizontal reactions close to the Fib entry
- Previous swing: confirmed swing high/low close to the Fib entry
- Trendline: swing-low projection for BUY and swing-high projection for SELL
- Psychological level: Fib entry close to a major round-number increment
- Candle confirmation: bullish directional confirmation for BUY, bearish directional confirmation for SELL

`Minimum confirmations` controls how many enabled POIs must actually be present before a setup passes.

## Local runtime files

```text
START_FX2ACTIVE.bat                 one-click Windows launcher
scripts/bootstrap.py                guided dependency/setup checks
scripts/run_fx2active.py            unified local runtime entry point
src/fx2active_bot/system_diagnostics.py
src/fx2active_bot/local_runtime.py
src/fx2active_bot/web_server.py
config/runtime_settings.json        editable strategy state
web/                                local dashboard
data/runtime/                       generated health/diagnostic state (not committed)
```

Generated local state and environments are ignored by Git through `.gitignore`.

## Developer setup

For development/testing rather than normal user startup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
python scripts/run_fx2active.py
```

## Current execution boundary

The local MT5 connection and worker health layer are implemented, but **live order submission is intentionally not enabled yet**. The exact FX2Active symbol(s), position-sizing rule, and final order-entry semantics still need to be specified before allowing this repository to submit real orders.

Until that execution layer is added, the worker safely monitors MT5 and applies/reflects the web-controlled strategy configuration without sending live broker orders.

`trading_enabled` defaults to `false` in the repository.

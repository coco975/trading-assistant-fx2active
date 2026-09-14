# Trading Assistant for FX2Active

A Windows-local M15 Fibonacci trading assistant with a simple browser control panel. No Vercel, Cloudflare Tunnel, public URL, web-control key, or remote settings service is required for this build.

## Normal use: one launcher

The person running the bot should not need to work from PowerShell or remember several commands.

On Windows, double-click:

```text
START_FX2ACTIVE.bat
```

That launcher handles:

```text
START_FX2ACTIVE.bat
        ↓
Check Python 3.11+
        ↓
Create isolated .venv if needed
        ↓
Explain missing dependencies
        ↓
Ask permission before installing them
        ↓
Run system diagnosis
        ↓
Verify MT5 terminal + logged-in account
        ↓
Verify localhost port + strategy settings
        ↓
Start local MT5 strategy worker
        ↓
Start localhost dashboard
        ↓
Open browser automatically
```

The dashboard is available only on that PC at:

```text
http://127.0.0.1:8080
```

Keep the launcher window open while the bot is running. `Ctrl+C` stops the local system.

## Guided dependency setup

The launcher never silently installs software. If something is missing, it explains what it is and asks `Y/N` first.

### Python

Python runs the strategy, diagnostics, MT5 bridge, and local web server. If Python is missing or older than 3.11, the launcher can offer to install Python 3.12 through Windows Package Manager (`winget`).

### Local `.venv`

The bot creates an isolated `.venv` folder so its Python packages do not interfere with the rest of the PC. The launcher asks before creating it.

### MetaTrader5 Python package

`MetaTrader5` is the Python bridge used to read MT5 prices, terminal/account state, positions, and M15 candles. It is installed only inside this bot's `.venv`, and the bootstrap explains it before requesting permission.

### MetaTrader 5 desktop terminal

The launcher does **not** silently install an MT5 desktop terminal. Different brokers can provide different branded MT5 terminals, so guessing a terminal would be unsafe. Diagnostics verify that a compatible MT5 terminal is installed, connected, and logged into the intended account.

The bot does not store the MT5 password in GitHub or return it through the dashboard. It uses the active MT5 terminal session and shows only a masked account number plus the broker server.

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

The dashboard also has a **Run system check** button so the same diagnosis can be repeated without using the command prompt.

The top status bar shows:

- Worker online/offline
- MT5 connected/not connected
- Account connected/not connected
- Open positions versus the configured maximum

## Web-controlled worker

Pressing **Done — Apply to Bot** writes validated settings to `config/runtime_settings.json`. The worker reloads those settings while evaluating the strategy, so changes take effect without rebuilding or restarting the bot.

The dashboard controls:

- Master trading enabled / disabled
- BUY enabled / disabled
- SELL enabled / disabled
- Exact MT5 trading symbol, including broker suffixes such as `EURUSD.a`
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
- Minimum POI confirmations required

## Local MT5 strategy evaluation

Once a valid Trading Symbol is entered, the local worker:

1. connects to the already logged-in MT5 terminal,
2. validates/selects the exact broker symbol,
3. reads the latest M15 candle history,
4. derives the symbol pip size from MT5 metadata,
5. counts current open account positions,
6. reloads the current dashboard settings,
7. evaluates the BUY/SELL 78.6% strategy and enabled POIs,
8. publishes the latest worker/setup state to the local dashboard.

The health/evaluation loop runs locally every few seconds. No public server is involved.

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
src/fx2active_bot/local_runtime.py  MT5 monitor + M15 strategy evaluator
src/fx2active_bot/web_server.py
config/runtime_settings.json        editable strategy state
web/                                local dashboard
data/runtime/                       generated health/diagnostic state (not committed)
```

Generated local state and environments are ignored through `.gitignore`.

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

The local worker now connects to MT5, reads live M15 market data, applies the web-controlled BUY/SELL strategy, checks the configured position cap, and detects qualifying setups.

**Live broker order submission is still intentionally disabled.** Before enabling real orders we still need the exact position-sizing rule and final execution semantics (for example whether the bot submits a pending limit at 78.6% or waits for the selected confirmation and sends a market order).

Until that is defined, the system evaluates the live strategy safely without submitting trades. `trading_enabled` defaults to `false` in the repository.

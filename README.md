# Trading Assistant for FX2Active

A lightweight M15 Fibonacci-retracement trading bot test project with a working web control panel.

## Core strategy

- Timeframe: M15
- Direction currently implemented: LONG only
- Fibonacci placement: bullish Swing Low -> Swing High
- Default Fib entry: 78.6% retracement
- Stop loss: 10 configurable pips below the 100% Fib / Swing Low
- Take profit: retracement high / 0% Fib / Swing High
- Maximum simultaneous positions: controlled from the web panel
- POI/confluence rules: controlled from the web panel
- Entry trigger: controlled from the web panel

## Web control panel

The test dashboard is intentionally simpler than the main trading-assistant dashboard. It has no separate trading web-control key.

The panel can control:

- Trading enabled / disabled
- Fibonacci rule enabled / disabled
- Fib retracement value (default 0.786)
- Stop-loss buffer in pips
- Take-profit mode (currently Swing High)
- Entry trigger:
  - First touch of the Fib zone
  - Touch then close back above the Fib level
  - Touch then bullish candle close
- Maximum open positions
- POI/confluence toggles:
  - Support / resistance
  - Previous swing level
  - Trendline
  - Psychological round-number level
  - Candle confirmation
- Minimum number of enabled POI confirmations required

When **Done — Apply to Bot** is pressed, the settings API validates and atomically saves the new configuration. `WebControlledLongFibStrategy` reloads those settings on every evaluation, so the next entry check uses the new rules without restarting the strategy process.

## POI implementation

The current POI code turns common price-action/confluence concepts into deterministic test heuristics. These are engineering definitions for this bot, not proprietary BabyPips algorithms.

- Support/resistance: repeated horizontal reactions close to the Fib entry
- Previous swing: confirmed swing high/low close to the Fib entry
- Trendline: projection through recent confirmed swing lows
- Psychological level: Fib entry close to a major round-number increment
- Candle confirmation: the latest candle touches the entry and gives a bullish close back at/above it

The toggles define which POI types are eligible. `Minimum confirmations` defines how many of the enabled POIs must actually be present before the setup passes.

## Runtime flow

```text
Web control panel
      ↓
POST /api/settings
      ↓
config/runtime_settings.json
      ↓
Worker / strategy reloads settings
      ↓
Trading enabled?
      ↓
Position limit available?
      ↓
78.6% Fib setup
      ↓
Enabled POI checks
      ↓
Selected entry trigger
      ↓
Eligible trade setup
```

## Price formulas

For a bullish impulse with Swing Low `L` and Swing High `H`:

```text
range = H - L
entry = H - (fib_retracement * range)
stop_loss = L - (stop_buffer_pips * pip_size)
take_profit = H
```

## Swing convention

The starter uses a five-candle swing/fractal convention:

- Swing High: the center candle high is greater than the highs of the two candles on each side.
- Swing Low: the center candle low is lower than the lows of the two candles on each side.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
python scripts/run_control_panel.py
```

Then open:

```text
http://127.0.0.1:8080
```

## Vercel

Vercel deployment is intentionally paused until the new Vercel account is ready. The interface and control architecture are already in the repository.

The current local settings store uses a JSON file so the full control loop can be tested immediately. A Vercel deployment should use a persistent remote settings store because a serverless filesystem is not a reliable place to persist bot configuration. The `RuntimeSettingsStore` boundary is isolated so that storage can be swapped without rebuilding the strategy or dashboard.

## Important

`pip_size` is configurable per instrument. Do not assume every symbol uses the same pip size.

The repository does not send live broker orders yet. Broker/MT5 execution should be connected only after the exact FX2Active symbol, account/execution requirements, sizing rule, and short-side rules are supplied.

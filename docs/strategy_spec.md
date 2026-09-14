# FX2Active Strategy Specification — v0.4

## Runtime model

This build is local-only. The same Windows PC runs:

- MetaTrader 5
- the FX2Active strategy worker
- system diagnostics
- the localhost web control panel

The dashboard binds to `127.0.0.1:8080`; no Vercel or Cloudflare tunnel is required.

## Timeframe

M15 only for this test build.

## Trading symbol

The exact broker symbol is set from the local web panel. Broker suffixes are supported, for example `EURUSD.a`.

The worker validates/selects that symbol in MT5, reads M15 rates directly from the connected terminal, and derives the symbol pip size from MT5 metadata.

## Direction

The bot supports both BUY and SELL setups. Either side can be enabled or disabled independently from the web control panel.

## Fibonacci placement

### BUY

For a completed bullish impulse:

1. Identify a confirmed Swing Low.
2. Identify the subsequent confirmed Swing High.
3. Draw Fibonacci from Swing Low to Swing High.
4. Treat Swing Low as 100%.
5. Treat Swing High as 0%.
6. Default entry retracement is 78.6%.

Let `L` be the swing low, `H` the swing high, and `R = H - L`:

```text
BUY entry = H - fib_retracement * R
BUY stop = L - stop_buffer_pips * pip_size
BUY target = H
```

### SELL

For a completed bearish impulse:

1. Identify a confirmed Swing High.
2. Identify the subsequent confirmed Swing Low.
3. Draw Fibonacci from Swing High to Swing Low.
4. Treat Swing High as 100%.
5. Treat Swing Low as 0%.
6. Default entry retracement is 78.6%.

Let `H` be the swing high, `L` the swing low, and `R = H - L`:

```text
SELL entry = L + fib_retracement * R
SELL stop = H + stop_buffer_pips * pip_size
SELL target = L
```

The web panel defaults `fib_retracement` to `0.786` and `stop_buffer_pips` to `10`.

## Stop loss

- BUY: default 10 pips below the 100% Fib / Swing Low.
- SELL: default 10 pips above the 100% Fib / Swing High.

## Take profit

- BUY: retracement Swing High / 0% Fib.
- SELL: retracement Swing Low / 0% Fib.

## Web-controlled runtime rules

The strategy reloads `config/runtime_settings.json` while evaluating the market. Pressing **Done — Apply to Bot** changes the next strategy evaluation without restarting the process.

Runtime controls include:

- master trading enabled switch
- BUY enabled switch
- SELL enabled switch
- exact MT5 symbol
- Fibonacci rule enabled switch
- Fibonacci retracement value
- stop buffer in pips
- maximum open positions
- entry trigger
- enabled POI categories
- minimum POI confirmations

## Entry triggers

The user can select one of three directional entry-trigger policies:

### `touch`

The latest M15 candle must trade through the calculated Fib entry.

### `close_back_in_direction`

- BUY: price touches the entry and closes back above it.
- SELL: price touches the entry and closes back below it.

### `directional_close`

- BUY: price touches the entry and the candle closes bullish at/above it.
- SELL: price touches the entry and the candle closes bearish at/below it.

## Points of interest / confluence

The following categories can be enabled or disabled individually:

- support / resistance
- previous swing level
- trendline
- psychological round-number level
- candle confirmation

Enabled categories are candidate confirmations. `min_confirmations` controls how many enabled categories must actually be present before a setup passes.

Directional confirmation is mirrored: bullish evidence is used for BUY setups and bearish evidence for SELL setups. Trendline logic uses swing lows for BUY and swing highs for SELL.

The current implementation uses deterministic test heuristics for each category. They are bot engineering definitions inspired by common technical-analysis concepts; they are not claimed to be proprietary BabyPips algorithms.

## Position limit

The local MT5 worker reads current account positions and compares their count with `max_open_positions`. If the configured limit is reached, a new setup is blocked.

This conservative test implementation counts all open MT5 positions because a bot-specific magic-number execution layer has not been defined yet.

## Diagnostics and startup

`START_FX2ACTIVE.bat` is the normal entry point. It checks Python, prepares the local `.venv`, explains missing dependencies before asking permission to install them, verifies MT5/account readiness, starts the worker, starts the web server, and opens the browser.

The dashboard can rerun the diagnosis with **Run system check**.

## Execution status

The worker currently performs live MT5 connectivity checks, reads live M15 candles, and evaluates qualifying BUY/SELL setups from the active website configuration.

Live broker order submission is intentionally disabled until the final position-sizing rule and exact order-entry semantics are supplied.

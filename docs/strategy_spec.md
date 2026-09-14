# FX2Active Strategy Specification — v0.2

## Timeframe

M15 only for this test build.

## Direction

LONG only in the current version.

## Fibonacci placement

For a completed bullish impulse:

1. Identify a confirmed Swing Low.
2. Identify the subsequent confirmed Swing High.
3. Draw Fibonacci from Swing Low to Swing High.
4. Treat Swing Low as 100%.
5. Treat Swing High as 0%.
6. Default entry retracement is 78.6%.

## Calculation

Let:

- `L` = swing low
- `H` = swing high
- `R = H - L`

Then:

```text
entry = H - fib_retracement * R
stop = L - stop_buffer_pips * pip_size
target = H
```

The web panel defaults `fib_retracement` to `0.786` and `stop_buffer_pips` to `10`.

## Web-controlled runtime rules

The strategy reloads `config/runtime_settings.json` on each evaluation. The web panel can change the active rule set without restarting the bot.

Runtime controls include:

- master trading enabled switch
- Fibonacci rule enabled switch
- Fibonacci retracement value
- stop buffer in pips
- maximum open positions
- entry trigger
- enabled POI categories
- minimum POI confirmations

## Entry triggers

The user can select one of three entry-trigger policies:

### `touch`

The latest candle must trade through the calculated Fib entry.

### `close_back_above`

The latest candle must trade at/below the Fib entry and then close above it.

### `bullish_close`

The latest candle must touch the Fib entry and close bullish at/above the entry.

## Points of interest / confluence

The following categories can be enabled or disabled individually:

- support / resistance
- previous swing level
- trendline
- psychological round-number level
- candle confirmation

Enabled categories are candidate confirmations. `min_confirmations` controls how many of the enabled categories must actually be present before a setup passes.

The current implementation uses deterministic test heuristics for each category. They are bot engineering definitions inspired by common technical-analysis concepts; they are not claimed to be proprietary BabyPips algorithms.

## Position limit

Before evaluating a new entry, the worker compares the number of currently open positions with `max_open_positions`. If the limit is already reached, no new setup is returned.

## Stop loss

Default: 10 pips below the 100% Fib / Swing Low. `pip_size` remains instrument configuration and is not globally hard-coded.

## Take profit

Current mode: Swing High / 0% Fib.

## Short trades

Not enabled yet. A mirrored bearish specification should be added only when the exact rules are supplied.

## Deployment status

The web interface is implemented in the repository but Vercel deployment is intentionally paused. Local persistence uses `config/runtime_settings.json`. Vercel deployment will require a persistent remote settings store so the web app and the trading worker share the same state reliably.

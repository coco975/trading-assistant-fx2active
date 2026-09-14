# FX2Active Strategy Specification — v0.3

## Timeframe

M15 only for this test build.

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

`pip_size` remains instrument configuration and is not globally hard-coded.

## Take profit

- BUY: retracement Swing High / 0% Fib.
- SELL: retracement Swing Low / 0% Fib.

## Web-controlled runtime rules

The strategy reloads `config/runtime_settings.json` on each evaluation. The web panel can change the active rule set without restarting the bot.

Runtime controls include:

- master trading enabled switch
- BUY enabled switch
- SELL enabled switch
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

The latest candle must trade through the calculated Fib entry.

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

Enabled categories are candidate confirmations. `min_confirmations` controls how many of the enabled categories must actually be present before a setup passes.

Directional confirmation is mirrored: bullish evidence is used for BUY setups and bearish evidence is used for SELL setups. Trendline logic uses swing lows for BUY and swing highs for SELL.

The current implementation uses deterministic test heuristics for each category. They are bot engineering definitions inspired by common technical-analysis concepts; they are not claimed to be proprietary BabyPips algorithms.

## Position limit

Before evaluating a new entry, the worker compares the number of currently open positions with `max_open_positions`. If the limit is already reached, no new setup is returned.

## Deployment status

The web interface is implemented in the repository but Vercel deployment is intentionally paused. Local persistence uses `config/runtime_settings.json`. Vercel deployment will require a persistent remote settings store so the web app and the trading worker share the same state reliably.

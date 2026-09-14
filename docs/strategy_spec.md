# FX2Active Strategy Specification — v0.1

## Timeframe

M15 only.

## Direction

LONG only in v0.1.

## Fibonacci placement

For a completed bullish impulse:

1. Identify a confirmed Swing Low.
2. Identify the subsequent confirmed Swing High.
3. Draw Fibonacci from Swing Low to Swing High.
4. Treat Swing Low as 100%.
5. Treat Swing High as 0%.
6. Use 78.6% as the deep retracement entry level.

## Calculation

Let:

- `L` = swing low
- `H` = swing high
- `R = H - L`

Then:

```text
entry = H - 0.786 * R
stop = L - 10 * pip_size
target = H
```

## Point of interest

A trade must ultimately require another point of interest/confluence at or around the 78.6% retracement.

The exact POI taxonomy and tolerance are pending user instructions. The code exposes a replaceable POI rule interface so these rules can be added without rewriting the Fibonacci engine.

## Entry trigger

Not finalized. The Fib engine calculates the intended entry level, but live execution is intentionally left open until the exact trigger is specified (pending order, touch, candle confirmation, etc.).

## Stop loss

10 pips below the 100% Fib / Swing Low. `pip_size` is instrument configuration, not hard-coded.

## Take profit

Swing High / 0% Fib.

## Short trades

Not enabled in v0.1. A mirrored bearish rule should only be added when explicitly specified.

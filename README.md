# Trading Assistant for FX2Active

Python starter for an M15 Fibonacci-retracement trading bot.

## Core strategy v0.1

- Timeframe: M15
- Direction implemented: LONG only
- Fibonacci placement: bullish Swing Low -> Swing High
- Fib entry: 78.6% retracement
- Stop loss: 10 configurable pips below the 100% Fib / Swing Low
- Take profit: retracement high / 0% Fib / Swing High
- POI confluence: pluggable; no POI rule is invented in v0.1
- Trade execution: adapter interface only; connect broker/platform after execution requirements are supplied

## Price formulas

For a bullish impulse with Swing Low `L` and Swing High `H`:

```text
range = H - L
entry_78_6 = H - 0.786 * range
stop_loss = L - 10 * pip_size
take_profit = H
```

## Swing convention

The starter includes a 5-candle swing/fractal convention:
- Swing High: the center candle high is greater than the highs of the two candles on each side.
- Swing Low: the center candle low is lower than the lows of the two candles on each side.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest
```

## Important

`pip_size` is configurable per instrument. Do not assume every symbol uses the same pip size.

The repository intentionally does not send live orders yet. Add the exact FX2Active/broker execution interface and the remaining POI rules before enabling live trading.

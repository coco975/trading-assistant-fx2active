# FX2Active Trading Assistant

FX2Active is a local MT5 trading assistant with a browser control panel for **Windows and macOS**.

## Before You Start

- Install MetaTrader 5.
- Log into the trading account you want FX2Active to use.
- Make sure your GitHub account has access to this private repository.

# Windows Setup

Open **PowerShell** and run these commands one at a time.

```powershell
cd $HOME\Documents
git clone https://github.com/coco975/trading-assistant-fx2active.git
cd trading-assistant-fx2active
.\START_FX2ACTIVE.bat
```

If `git` is not installed:

```powershell
winget install --id Git.Git -e
```

Then close PowerShell, open it again, and run the setup commands above.

### Start it again later

```powershell
cd $HOME\Documents\trading-assistant-fx2active
git pull
.\START_FX2ACTIVE.bat
```

# macOS Setup

Open **Terminal** and run these commands one at a time.

```bash
cd ~/Documents
git clone https://github.com/coco975/trading-assistant-fx2active.git
cd trading-assistant-fx2active
chmod +x START_FX2ACTIVE_MAC.command
./START_FX2ACTIVE_MAC.command
```

If macOS asks to install Command Line Tools/Git, allow it and then run the commands again.

On the first Mac setup, FX2Active uses `FX2ActiveBridge.mq5` to connect the local app to MT5. Follow the launcher instructions to compile it in MetaEditor, attach **FX2ActiveBridge** to one MT5 chart, and enable Algo Trading.

### Start it again later

```bash
cd ~/Documents/trading-assistant-fx2active
git pull
./START_FX2ACTIVE_MAC.command
```

# Dashboard Access

When FX2Active starts, choose:

- **1 — This computer only**: use the dashboard only on the PC/Mac running FX2Active.
- **2 — Same Wi-Fi/LAN**: open the dashboard from another phone, tablet, or computer on the same private network.

For option 2, the launcher shows a dashboard address and PIN. Open the address on the other device and enter the PIN once. You stay signed in for that browser session.

# Web Interface

- **Trading enabled** — master switch for allowing new setups.
- **Worker / MT5 / Account** — shows whether FX2Active, MT5, and the trading account are connected.
- **Trading symbol** — enter the exact MT5 symbol, for example `EURUSD`, `XAUUSD`, or the broker's version such as `XAUUSD.x`.
- **BUY / SELL** — choose which trade directions FX2Active may use.
- **Fib retracement** — strategy retracement level. Default is `0.786`.
- **Stop buffer** — extra pips beyond the swing used for the stop loss.
- **Confirmation trigger** — decides what must happen at the Fib level before a setup qualifies.
- **Maximum open positions** — maximum number of positions allowed at once.
- **Risk %** — risk a percentage of account equity per trade.
- **Fixed lot** — always use the selected lot size.
- **Fixed cash** — risk a fixed amount in the MT5 account currency.
- **Market after confirmation** — enter after the selected confirmation trigger.
- **Pending at 78.6%** — use the Fib price as the intended pending-entry level.
- **Points of Interest** — extra confirmations such as support/resistance, previous swing, trendline, round-number level, and candle confirmation.
- **Minimum confirmations** — how many enabled POIs must agree before the setup qualifies.
- **Run system check** — checks the computer, MT5 connection, account, and FX2Active setup.
- **Done — Apply to Bot** — saves the settings and applies them to the worker.

# Stop FX2Active

Keep the launcher/Terminal window open while FX2Active is running.

Press:

```text
Ctrl + C
```

> Live broker order submission is currently disabled while the execution layer is being completed and tested.

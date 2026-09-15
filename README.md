# FX2Active Trading Assistant

FX2Active is a local MT5 trading assistant with a browser control panel for **Windows and macOS**.

## Before You Start

- Install MetaTrader 5 and log into the account you want FX2Active to use.
- Keep MT5 open while FX2Active is running.
- Start with a **demo account** until the execution tests on your own MT5 installation are complete.

# Windows Setup

Open **PowerShell** and run:

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

### Start/update later

```powershell
cd $HOME\Documents\trading-assistant-fx2active
git pull
.\START_FX2ACTIVE.bat
```

FX2Active checks Python, the local environment, MT5 connectivity, trading permissions, settings and the dashboard port before starting.

# macOS Setup

Keep your broker's MT5 app open, then open **Terminal** and run:

```bash
cd ~/Documents
git clone https://github.com/coco975/trading-assistant-fx2active.git
cd trading-assistant-fx2active
chmod +x START_FX2ACTIVE_MAC.command
./START_FX2ACTIVE_MAC.command
```

If macOS asks to install Command Line Tools/Git, allow it and run the commands again.

FX2Active automatically tries to locate broker-branded MT5/Wine data folders, creates `MQL5/Experts/FX2Active`, and copies the latest `FX2ActiveBridge.mq5` there.

The first time the bridge changes, one MetaEditor step is still required:

1. Open MetaEditor from MT5.
2. Open `Experts > FX2Active > FX2ActiveBridge.mq5`.
3. Press **Compile** (`F7` or `Fn + F7`).
4. Attach **FX2ActiveBridge** to one MT5 chart.
5. Turn **Algo Trading** on and leave that chart open.

### Start/update later

```bash
cd ~/Documents/trading-assistant-fx2active
git pull
./START_FX2ACTIVE_MAC.command
```

The launcher checks whether the installed bridge source or compiled `.ex5` is stale and tells you when another compile is needed.

# Dashboard Access

When FX2Active starts, choose:

- **1 — This computer only** — dashboard only on the PC/Mac running FX2Active.
- **2 — Same Wi-Fi/LAN** — dashboard available to another device on the same private network using a temporary PIN.

Do not expose port `8080` through router port forwarding or a public tunnel.

# Main Controls

- **Trading enabled** — lets the strategy look for new entries.
- **Execute orders in MT5** — separately arms broker/demo order submission.
- **Allow real/live account** — separately permits execution on a real account. Keep this OFF while demo testing.
- **Trading symbol** — use the exact broker symbol, such as `XAUUSDm` or `XAUUSD.x`.
- **BUY / SELL** — allowed directions.
- **Fib retracement** — default `0.786`.
- **Stop buffer** — extra pips beyond the swing for SL.
- **Risk % / Fixed lot / Fixed cash** — position-sizing mode.
- **Market after confirmation** — submit a market order after the configured confirmation.
- **Pending at 78.6%** — place a limit order at the Fib entry.
- **Maximum open positions** — global FX2Active exposure limit.
- **Maximum spread** — blocks execution when spread is too high; `0` disables this guard.
- **Maximum deviation** — MT5 order deviation in points.
- **Run system check** — checks computer, MT5, account, permissions and the current bridge.

FX2Active uses magic number `26091501` and comment `FX2Active` so its own positions/orders can be distinguished from manual trades.

# First Demo Execution Check

Before relying on automated execution:

1. Use a demo account.
2. Run **System Check** and make sure MT5/account/bridge checks are healthy.
3. Keep **Allow real/live account** OFF.
4. Start with the broker minimum practical lot/risk.
5. Enable **Trading enabled** and **Execute orders in MT5**.
6. Verify the first order inside MT5: side, symbol, volume, entry, SL, TP and FX2Active ownership.
7. Restart FX2Active and confirm the same setup is not submitted twice.
8. Test disconnect/reconnect behavior before considering any real account.

# Stop FX2Active

Keep the launcher/Terminal window open while FX2Active is running. Press:

```text
Ctrl + C
```

Order execution is implemented, but **real-account permission remains OFF by default** and should stay OFF until the demo execution checks pass on your own MT5 installation.

# FX2Active Trading Assistant

FX2Active is a local MT5 trading assistant with a browser control panel for **Windows and macOS**.

## Before You Start

- Install MetaTrader 5 and log into the account you want FX2Active to use.
- Keep MT5 open while FX2Active is running.
- Start with a **demo account** until execution is proven on the actual broker installation.

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

FX2Active checks Python, its local environment, MT5 connectivity, trading permissions, settings and the dashboard port before starting.

# macOS Setup

FX2Active supports MetaTrader 5 installed from the normal web installer, including broker-branded Wine installations.

Open **Terminal** and run:

```bash
cd ~/Documents
git clone https://github.com/coco975/trading-assistant-fx2active.git
cd trading-assistant-fx2active
chmod +x START_FX2ACTIVE_MAC.command
./START_FX2ACTIVE_MAC.command
```

If macOS asks to install Command Line Tools/Git, allow it and run the commands again.

On startup FX2Active automatically tries to:

- find the installed MetaTrader/broker app;
- locate its Wine `drive_c` data prefix;
- detect the actual MT5 installation even if `MQL5` has not been created yet;
- create `MQL5/Experts/FX2Active` itself;
- copy the current `FX2ActiveBridge.mq5` into that folder;
- find the bundled Wine/MetaEditor executable and compile the bridge automatically;
- detect an old bridge and require the current trade-capable version before execution.

A normal web-installed MT5 under the user's Library should not require `sudo` or manual root-owned folder creation.

If automatic MetaEditor compilation is unavailable on a particular broker package, FX2Active still creates the folders and installs the source. The only fallback step is opening `Experts > FX2Active > FX2ActiveBridge.mq5` in MetaEditor and pressing **Compile** once.

The EA must be attached to one MT5 chart and **Algo Trading** enabled. FX2Active detects when either of those is missing and blocks order execution until the bridge is healthy.

### Start/update later

```bash
cd ~/Documents/trading-assistant-fx2active
git pull
./START_FX2ACTIVE_MAC.command
```

# Dashboard Access

When FX2Active starts, choose:

- **1 — This computer only** — dashboard only on the PC/Mac running FX2Active.
- **2 — Same Wi-Fi/LAN** — dashboard available to another device on the same private network using a temporary PIN.

Do not expose port `8080` through router port forwarding or a public tunnel.

# Dashboard

The dashboard includes:

- **Current Fibonacci Setup** — direction, swing high/low, swing times, entry, SL, TP and reward/risk.
- **Fib Levels** — live price positions from swing high to swing low, including 23.6%, 38.2%, 50%, 61.8%, 71%, the configured entry and 100%.
- **Trade Log** — setup detection, MT5 execution, closed trades, exit reason and net P/L after commission, swap and fees.
- **System Check** — computer, MT5, account, permissions and bridge readiness.

Main controls are **Trading Active**, **MT5 Execution**, **Live Account Access**, symbol, BUY/SELL, risk sizing, entry confirmation, maximum exposure, spread and deviation.

FX2Active uses magic number `26091501` and comment `FX2Active` so its own positions/orders and closed deals can be separated from manual trading.

# First Demo Execution Check

Before relying on automated execution:

1. Use a demo account.
2. Run **System Check** and make sure MT5/account/bridge checks are healthy.
3. Keep **Live Account Access** OFF.
4. Start with the broker minimum practical lot/risk.
5. Enable **Trading Active** and **MT5 Execution**.
6. Verify the first order inside MT5: side, symbol, volume, entry, SL, TP and FX2Active ownership.
7. Confirm the closed result and P/L appear in **Trade Log**.
8. Restart FX2Active and confirm the same setup is not submitted twice.
9. Test disconnect/reconnect behavior before considering any real account.

# Stop FX2Active

Keep the launcher/Terminal window open while FX2Active is running. Press:

```text
Ctrl + C
```

Real-account permission is **OFF by default** and should stay OFF until demo execution has been proven on the actual broker terminal.

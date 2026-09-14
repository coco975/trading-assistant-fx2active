# FX2Active Trading Assistant

FX2Active is a local trading assistant for MT5 with a browser control panel.

It supports:
- Windows
- macOS
- Local dashboard access
- Same-Wi-Fi dashboard access
- BUY and SELL setup detection
- M15 78.6% Fibonacci strategy settings
- Risk %, fixed lot, and fixed cash sizing

## Main files

- `START_FX2ACTIVE.bat` — Windows launcher
- `START_FX2ACTIVE_MAC.command` — macOS launcher
- `bridge/FX2ActiveBridge.mq5` — macOS MT5 bridge
- `config/runtime_settings.json` — saved bot settings
- `web/` — dashboard files

# Windows Setup

## First time

1. Install MetaTrader 5.
2. Open MT5 and log into the trading account.
3. Download or clone this repository.
4. Open the FX2Active folder.
5. Double-click `START_FX2ACTIVE.bat`.
6. Approve Python/dependency installation if asked.
7. Choose dashboard access:
   - `1` = this PC only
   - `2` = devices on the same Wi-Fi/LAN
8. Wait for the system checks to finish.
9. The dashboard opens automatically.
10. Set the MT5 symbol, risk, BUY/SELL settings, and strategy options.
11. Press **Done - Apply to Bot**.

## Normal Windows use

1. Open MT5.
2. Log into the correct account.
3. Double-click `START_FX2ACTIVE.bat`.
4. Choose dashboard access.
5. Leave the launcher window open while FX2Active is running.

# macOS Setup

## First time

1. Install MetaTrader 5 for Mac.
2. Open MT5 and log into the trading account.
3. Download or clone this repository.
4. Open the FX2Active folder.
5. Double-click `START_FX2ACTIVE_MAC.command`.
6. Approve Python/dependency installation if asked.
7. Let FX2Active copy `FX2ActiveBridge.mq5` into MT5 when detected.
8. Open MetaEditor from MT5.
9. Find `FX2ActiveBridge.mq5` under Experts/FX2Active.
10. Compile it.
11. Return to MT5.
12. Attach **FX2ActiveBridge** to one chart.
13. Enable Algo Trading.
14. Keep that chart open.
15. Run `START_FX2ACTIVE_MAC.command` again if needed.
16. Choose dashboard access:
   - `1` = this Mac only
   - `2` = devices on the same Wi-Fi/LAN
17. Wait for the system checks to finish.
18. Configure the dashboard and press **Done - Apply to Bot**.

## Normal Mac use

1. Open MT5.
2. Make sure **FX2ActiveBridge** is attached and running.
3. Double-click `START_FX2ACTIVE_MAC.command`.
4. Choose dashboard access.
5. Leave the launcher window open while FX2Active is running.

# Dashboard Access

## This computer only

Open:

```text
http://127.0.0.1:8080
```

## Another device on the same Wi-Fi

Choose option `2` when starting FX2Active.

The launcher will show an address like:

```text
http://192.168.1.25:8080
```

It will also show a temporary PIN.

On the second device:

1. Connect to the same Wi-Fi.
2. Open the address shown by FX2Active.
3. Enter the PIN once.
4. Stay signed in for that browser session.

# Stop FX2Active

In the launcher window press:

```text
Ctrl + C
```

# Important

- Keep MT5 open while FX2Active is running.
- Do not expose port `8080` using router port forwarding.
- Live broker order submission is currently disabled while the execution layer is being completed and tested.

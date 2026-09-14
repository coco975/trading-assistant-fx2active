# FX2Active Trading Assistant

FX2Active is a local M15 78.6% Fibonacci trading assistant with a browser control panel. It is designed to run on both Windows and macOS while keeping MT5 and the strategy worker on the same computer.

## Supported platforms

### Windows

Run `START_FX2ACTIVE.bat`.

Windows uses MetaQuotes' `MetaTrader5` Python package to communicate directly with the locally installed MT5 terminal.

### macOS

Run `START_FX2ACTIVE_MAC.command`.

MetaTrader 5 for macOS runs under MetaQuotes' Wine-based installer. Native macOS Python does not use the Windows MT5 IPC package, so FX2Active includes `bridge/FX2ActiveBridge.mq5`.

On first setup, the launcher attempts to copy the bridge source into detected MT5 `MQL5/Experts/FX2Active` folders. In MetaEditor, compile `FX2ActiveBridge.mq5`, attach it to one chart, enable Algo Trading, and leave that chart open. The EA writes local account, symbol, M15 candle and broker-volume data into MT5's `FILE_COMMON` folder. Native macOS Python reads that local bridge data and evaluates the same strategy code used on Windows.

No broker password is stored by FX2Active.

## First run

1. Install/open the broker's MT5 terminal and log into the intended account.
2. Start the launcher for the operating system.
3. Read and approve any dependency installation prompts.
4. FX2Active creates a private `.venv` for its packages.
5. Choose dashboard access: this computer only, or trusted devices on the same private Wi-Fi/LAN.
6. Wait for diagnostics to pass.
7. Configure the exact MT5 symbol, BUY/SELL permissions, risk/lot settings, execution mode and strategy options in the dashboard.
8. Press **Done - Apply to Bot**.

## Private Wi-Fi / LAN dashboard

LAN mode binds the dashboard to the computer's private network and prints an address such as `http://192.168.1.25:8080` plus a temporary six-digit access PIN.

The remote device opens the address and gets an FX2Active login page. After the PIN is accepted, the server creates an HttpOnly, SameSite=Strict browser-session cookie. The user is not asked for the PIN again during that browser session. Closing the browser session or restarting FX2Active ends the session.

LAN mode rejects public-source IP addresses. Do not configure router port forwarding for port 8080.

## Strategy runtime

The shared strategy engine supports BUY and SELL M15 78.6% Fibonacci retracement setups, web-controlled POI/confirmation settings, position caps, risk-percent/fixed-lot/fixed-cash sizing and market-vs-pending execution preferences.

Windows position sizing uses MT5's `order_calc_profit()` where required. macOS uses broker-provided tick-size and loss-tick-value data exported by the local MQL5 bridge.

## Current execution boundary

The current build evaluates live MT5 data and calculates planned position sizes on both platforms. Broker order submission remains intentionally disabled until the live execution adapter, duplicate-entry protection, bot ownership/magic number, spread/slippage guards and pending-order behavior are implemented and tested on target accounts.

## Stop FX2Active

Keep the launcher window open while FX2Active is running. Press `Ctrl+C` in that window to stop the worker and dashboard.

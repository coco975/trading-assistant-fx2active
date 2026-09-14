@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title FX2Active Trading Assistant

echo.
echo ================================================
echo   FX2Active Trading Assistant - Local Launcher
echo ================================================
echo.
echo This launcher checks the PC, prepares the bot, verifies MT5,
echo starts the strategy worker and opens the control website.
echo No router port forwarding or public hosting is used.
echo.

set "PY_CMD="

rem Prefer the normal python.exe command first. Some PCs have a broken
rem Windows py launcher even though Python itself is installed correctly.
python --version >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"

rem Only try the Windows Python launcher when python.exe was not found.
if not defined PY_CMD (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD goto :install_python

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [MISSING] The installed Python is older than 3.11.
  echo Python 3.11 or newer is required by this bot.
  echo.
  choice /C YN /N /M "Install Python 3.12 using Windows Package Manager? [Y/N]: "
  if errorlevel 2 goto :no_python
  goto :winget_python
)

echo [OK] Python detected:
%PY_CMD% --version
goto :python_ready

:install_python
echo [MISSING] Python 3 is not installed or is not on PATH.
echo Python runs the trading bot, diagnostics, MT5 connection and local website.
echo.
choice /C YN /N /M "Install Python 3.12 using Windows Package Manager? [Y/N]: "
if errorlevel 2 goto :no_python
goto :winget_python

:winget_python
where winget >nul 2>&1
if errorlevel 1 (
  echo.
  echo Windows Package Manager ^(winget^) is not available.
  echo Install Python 3.12 manually from python.org, then run this file again.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
echo.
echo Python setup command finished.
echo Close this window, open a new PowerShell window, then run START_FX2ACTIVE.bat again.
pause
exit /b 0

:python_ready
if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] The bot needs its own isolated Python environment.
  echo This keeps its packages separate from the rest of the PC and can be deleted safely.
  echo.
  choice /C YN /N /M "Create the local .venv environment now? [Y/N]: "
  if errorlevel 2 (
    echo Setup cancelled. Nothing was installed.
    pause
    exit /b 1
  )
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo Failed to create the Python environment.
    pause
    exit /b 1
  )
)

echo.
echo ------------------------------------------------
echo Dashboard access
echo ------------------------------------------------
echo [1] This PC only
echo [2] Devices on the same private Wi-Fi / LAN
choice /C 12 /N /M "Choose 1 or 2: "
if errorlevel 2 goto :lan_access

set "FX2ACTIVE_ACCESS_MODE=local"
set "FX2ACTIVE_DASHBOARD_PIN="
echo [OK] Dashboard will be available on this PC only.
goto :start_bot

:lan_access
set "FX2ACTIVE_ACCESS_MODE=lan"
set "FX2ACTIVE_DASHBOARD_PIN="
for /f "delims=" %%P in ('%PY_CMD% -c "import secrets; print(secrets.randbelow(900000)+100000)"') do set "FX2ACTIVE_DASHBOARD_PIN=%%P"
if not defined FX2ACTIVE_DASHBOARD_PIN (
  echo [ERROR] Could not generate the private dashboard access PIN.
  pause
  exit /b 1
)
echo.
echo [OK] Private Wi-Fi / LAN dashboard mode selected.
echo Temporary access PIN: %FX2ACTIVE_DASHBOARD_PIN%
echo Enter this PIN once on the other device; it remains signed in for that browser session.
echo.
echo IMPORTANT: If Windows Firewall asks about Python network access,
echo allow PRIVATE networks only. Do not enable router port forwarding.

goto :start_bot

:start_bot
".venv\Scripts\python.exe" scripts\bootstrap.py
set "EXIT_CODE=%errorlevel%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo FX2Active stopped with an error. Read the message above for the exact reason.
  pause
)
exit /b %EXIT_CODE%

:no_python
echo Installation cancelled. Nothing was changed.
pause
exit /b 1

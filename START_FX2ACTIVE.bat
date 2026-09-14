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
 echo starts the strategy worker and opens the local control website.
 echo Nothing is hosted on the public internet.
 echo.

set "PY_CMD="
py -3 --version >nul 2>&1
if %errorlevel%==0 set "PY_CMD=py -3"

if not defined PY_CMD (
  python --version >nul 2>&1
  if %errorlevel%==0 set "PY_CMD=python"
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
 echo Python installation finished. Close this window and run START_FX2ACTIVE.bat again.
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

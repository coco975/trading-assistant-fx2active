@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title FX2Active Trading Assistant

echo.
echo ================================================
echo   FX2Active Trading Assistant - Windows Launcher
echo ================================================
echo.
echo This launcher checks Python, the local environment, MT5,
echo starts the strategy worker and opens the control website.
echo No router port forwarding or public hosting is used.
echo.

set "PY_CMD="

rem Prefer python.exe. Some PCs have a broken py launcher even when Python works.
python --version >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"

if not defined PY_CMD (
  py -3 --version >nul 2>&1
  if not errorlevel 1 set "PY_CMD=py -3"
)

if not defined PY_CMD goto :install_python

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [MISSING] The installed Python is older than 3.11.
  echo Python 3.11 or newer is required by FX2Active.
  echo.
  choice /C YN /N /M "Install Python 3.13 using Windows Package Manager? [Y/N]: "
  if errorlevel 2 goto :no_python
  goto :winget_python
)

echo [OK] Python detected:
%PY_CMD% --version
goto :python_ready

:install_python
echo [MISSING] Python 3.11 or newer is not installed or is not on PATH.
echo.
choice /C YN /N /M "Install Python 3.13 using Windows Package Manager? [Y/N]: "
if errorlevel 2 goto :no_python
goto :winget_python

:winget_python
where winget >nul 2>&1
if errorlevel 1 (
  echo.
  echo Windows Package Manager ^(winget^) is not available.
  echo Install Python 3.11+ manually from python.org, then run this file again.
  pause
  exit /b 1
)
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo [ERROR] Python installation did not complete successfully.
  pause
  exit /b 1
)
echo.
echo Python installation completed.
echo Close this window, open a new PowerShell window, then run START_FX2ACTIVE.bat again.
pause
exit /b 0

:python_ready
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo [REPAIR] Existing .venv is broken or uses unsupported Python. Rebuilding it...
    rmdir /S /Q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating the private FX2Active Python environment...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create the Python environment.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [REPAIR] pip is missing from .venv. Repairing it locally...
  ".venv\Scripts\python.exe" -m ensurepip --upgrade
  if errorlevel 1 (
    echo [ERROR] Could not repair pip inside .venv.
    pause
    exit /b 1
  )
)

echo [OK] Local Python environment is healthy.
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
for /f "delims=" %%P in ('".venv\Scripts\python.exe" -c "import secrets; print(secrets.randbelow(900000)+100000)"') do set "FX2ACTIVE_DASHBOARD_PIN=%%P"
if not defined FX2ACTIVE_DASHBOARD_PIN (
  echo [ERROR] Could not generate the private dashboard access PIN.
  pause
  exit /b 1
)
echo.
echo [OK] Private Wi-Fi / LAN dashboard mode selected.
echo Temporary access PIN: %FX2ACTIVE_DASHBOARD_PIN%
echo Enter this PIN once on the other device for that browser session.
echo.
echo IMPORTANT: If Windows Firewall asks about Python network access,
echo allow PRIVATE networks only. Do not enable router port forwarding.

goto :start_bot

:start_bot
set "PYTHONUNBUFFERED=1"
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

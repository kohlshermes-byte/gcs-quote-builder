@echo off
setlocal EnableExtensions
REM Double-click this to start the GCS Quote Builder.
REM It opens your browser automatically. Keep this window open while you work.
REM Close the window to stop the app.
cd /d "%~dp0"

REM Stop stale copies so the browser hits the latest code (not an old server on 8765).
echo Stopping any previous GCS Quote Builder instances...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'app\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul
timeout /t 1 /nobreak >nul

REM Use the real Python launcher by full path (avoids the Microsoft Store stub).
set "PY=%LOCALAPPDATA%\Programs\Python\Launcher\py.exe"
set "PY_ARGS=-3"
if not exist "%PY%" (
  set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  set "PY_ARGS="
)

if not exist "%PY%" (
  echo.
  echo Python 3 is not installed on this PC.
  echo.
  echo 1. Download from https://www.python.org/downloads/
  echo 2. During install, check "Add Python to PATH"
  echo 3. Run this file again
  echo.
  pause
  exit /b 1
)

REM Make sure required libraries are present (one-time on first run).
set NEED_INSTALL=0
"%PY%" %PY_ARGS% -c "import docx" 2>nul || set NEED_INSTALL=1
"%PY%" %PY_ARGS% -c "import reportlab" 2>nul || set NEED_INSTALL=1
"%PY%" %PY_ARGS% -c "import requests" 2>nul || set NEED_INSTALL=1
if "%NEED_INSTALL%"=="1" (
  echo Setting up for first use, one moment... ^(downloading components^)
  if exist "%~dp0requirements.txt" (
    "%PY%" %PY_ARGS% -m pip install --quiet -r "%~dp0requirements.txt"
  ) else (
    "%PY%" %PY_ARGS% -m pip install --quiet python-docx reportlab requests
  )
  if errorlevel 1 (
    echo.
    echo Setup could not download the required components.
    echo Make sure this computer is connected to the internet for this first run,
    echo then try again. ^(After the first run, no internet is needed.^)
    pause
    exit /b 1
  )
)

"%PY%" %PY_ARGS% app.py
if errorlevel 1 (
  echo.
  echo The app stopped with an error. See the message above.
)
pause

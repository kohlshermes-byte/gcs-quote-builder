#!/bin/bash
# Double-click this to start the GCS Quote Builder.
# It opens your browser automatically. Keep the Terminal window open while you work.
# Close the window (or press Ctrl-C) to stop.
cd "$(dirname "$0")"

# Stop stale copies so the browser hits the latest code.
echo "Stopping any previous GCS Quote Builder instances..."
pkill -f "python.*app.py" 2>/dev/null || true
sleep 1

# Find a Python 3
PY=""
for c in python3 python; do
  if command -v $c >/dev/null 2>&1; then PY=$c; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ then try again."
  read -p "Press Enter to close."
  exit 1
fi

# Make sure required libraries are present (one-time on first run).
need_install=0
$PY -c "import docx" 2>/dev/null || need_install=1
$PY -c "import reportlab" 2>/dev/null || need_install=1
$PY -c "import requests" 2>/dev/null || need_install=1
$PY -c "import playwright" 2>/dev/null || need_install=1
if [ "$need_install" -eq 1 ]; then
  echo "Setting up for first use, one moment... (downloading components)"
  if [ -f "requirements.txt" ]; then
    $PY -m pip install --quiet -r requirements.txt
  else
    $PY -m pip install --quiet python-docx reportlab requests playwright
  fi
  if [ $? -ne 0 ]; then
    echo ""
    echo "Setup could not download the required components."
    echo "Make sure this computer is connected to the internet for this first run,"
    echo "then try again. (Conveyor extract requires internet when scraping.)"
    read -p "Press Enter to close."
    exit 1
  fi
fi

# Playwright needs a Chromium browser binary for Save Screenshot.
unset PLAYWRIGHT_BROWSERS_PATH
if ! $PY -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
  :
elif ! $PY -c "
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
try:
    b = p.chromium.launch(headless=True)
    b.close()
finally:
    p.stop()
" 2>/dev/null; then
  echo "Installing Chromium for Save Screenshot (one-time)…"
  $PY -m playwright install chromium
  if [ $? -ne 0 ]; then
    echo "Warning: Chromium install failed. Save Screenshot may not work until you run:"
    echo "  python3 -m playwright install chromium"
  fi
fi

$PY app.py

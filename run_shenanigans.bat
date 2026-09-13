@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==================================================
echo   HOSKO'S SHADY SHENANIGANS - ONE BUTTON COMPANY
echo ==================================================
echo.
echo One console. One dashboard. One six-hour workday.
echo Worker agents + Raptor/Apex/Circuit start together.
echo Trading remains PAPER ONLY.
echo.

python -c "import PIL" >nul 2>&1
if errorlevel 1 (
  echo Installing the character animation dependency once...
  python -m pip install "Pillow>=11.0.0"
  if errorlevel 1 (
    echo Could not install Pillow. Mission Control cannot start.
    pause
    exit /b 1
  )
)

start "" /b python -m backend.dashboard
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765
python -m backend.company_day --start --hours 6

echo.
echo Company day launched in the background.
echo Keep this window open for Mission Control logs, or use the RUN button later.
echo Dashboard: http://127.0.0.1:8765
echo.
pause

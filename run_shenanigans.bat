@echo off
setlocal
cd /d "%~dp0"

echo.
echo ================================================
echo   HOSKO'S SHADY SHENANIGANS - MISSION CONTROL
echo ================================================
echo.
echo Starting dashboard and one 6-hour company workday.
echo Worker agents + Raptor/Apex/Circuit start together.
echo Trading is PAPER ONLY.
echo.

start "Hosko's Shady Shenanigans - Mission Control" /D "%~dp0" cmd /k python -m backend.dashboard
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765

python -m backend.company_day --start --hours 6

echo.
echo Mission Control is running.
echo You can start a new workday later with the RUN button when this one is finished.
pause

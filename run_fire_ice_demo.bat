@echo off
setlocal
cd /d "%~dp0"
echo.
echo ============================================
echo  DARWIN INDUSTRIES - FIRE AND ICE DEMO
echo ============================================
echo.
echo This will:
echo  1. open Mission Control in a second CMD,
echo  2. simulate an accepted website quotation,
echo  3. let the agents research, review, QA and build,
echo  4. open the finished staging website in your browser.
echo.
echo No real payment or revenue is recorded.
echo.

start "Darwin Mission Control" /D "%~dp0" cmd /k python -m backend.dashboard
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765

python -m backend.website_job --demo --business-name "Fire & Ice Wellbeing" --website "https://www.fireandicewellbeing.com/"

echo.
echo Darwin Website Studio stopped.
echo Mission Control may still be open in its own CMD window.
pause

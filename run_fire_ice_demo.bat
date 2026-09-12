@echo off
setlocal
cd /d "%~dp0"
echo.
echo ============================================
echo  DARWIN INDUSTRIES - FIRE AND ICE DEMO
echo ============================================
echo.
echo This will simulate an accepted website quotation,
echo build a premium staging site, QA it, and open it locally.
echo No real payment or revenue is recorded.
echo.
python -m backend.website_job --demo --business-name "Fire & Ice Wellbeing" --website "https://www.fireandicewellbeing.com/"
echo.
echo Darwin Website Studio stopped.
pause

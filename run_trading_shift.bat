@echo off
setlocal
cd /d "%~dp0"

echo.
echo ============================================
echo  HOSKO'S SHADY SHENANIGANS - 6 HOUR PAPER SHIFT
echo ============================================
echo.
echo Raptor: adaptive Solana meme trading (paper only)
echo Apex: intraday equities if Alpaca paper data is configured
echo Circuit: independent risk control
echo.
echo REAL MONEY EXECUTION IS DISABLED.
echo This launcher uses DEX-route paper fee assumptions so tiny
echo Moonshot-app minimum fees do not make the qualification test meaningless.
echo.

set DARWIN_TRADING_MODE=paper
set DARWIN_MEME_SIM_FEE_MODE=dex_route
set DARWIN_MEME_PAPER_ACCOUNT_USD=100
set DARWIN_MEME_PAPER_NOTIONAL_USD=40
set DARWIN_MEME_PAPER_DAILY_STOP_USD=6
set DARWIN_MEME_MAX_OPEN_TRADES=3
set DARWIN_MEME_CANDIDATES=10
set DARWIN_MEME_MIN_LIQUIDITY_USD=15000
set DARWIN_MEME_SIM_ROUTE_FEE_BPS_PER_SIDE=30
set DARWIN_MEME_SIM_NETWORK_FEE_USD_ROUND_TRIP=0.02
set DARWIN_MEME_SIM_SLIPPAGE_BPS=35

start "Hosko's Shady Shenanigans Mission Control" /D "%~dp0" cmd /k python -m backend.dashboard
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765

python -m backend.trading_desk --hours 6 --interval-minutes 3 --max-model-calls 120

echo.
echo Six-hour paper shift ended.
pause

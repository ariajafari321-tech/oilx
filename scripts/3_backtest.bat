@echo off
call "%~dp0_env.bat"
cd /d "%OILX_DIR%"
"%PY%" -m oilx backtest
start "" "%OILX_DIR%\data\out\tearsheet.html"
pause

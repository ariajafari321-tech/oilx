@echo off
call "%~dp0_env.bat"
cd /d "%OILX_DIR%"
"%PY%" -m oilx kalshi-scan
"%PY%" -m oilx kalshi-demo
pause

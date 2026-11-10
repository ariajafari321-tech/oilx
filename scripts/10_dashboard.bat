@echo off
call "%~dp0_env.bat"
cd /d "%OILX_DIR%"
start "" http://127.0.0.1:8766
"%PY%" -m oilx serve
pause

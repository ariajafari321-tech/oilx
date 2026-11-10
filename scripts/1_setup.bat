@echo off
call "%~dp0_env.bat"
echo === oilx setup: venv at %VENV% ===
if not exist "%PY%" python -m venv "%VENV%"
"%PY%" -m pip install --upgrade pip -q
"%PY%" -m pip install -r "%OILX_DIR%\requirements.txt" -q
cd /d "%OILX_DIR%"
"%PY%" -m pytest -q
echo === done. next: 2_fetch.bat (refresh data) or 3_backtest.bat ===
pause

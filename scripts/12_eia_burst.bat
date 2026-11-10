@echo off
rem EIA release burst: scan + trade every 2 minutes for 70 minutes, instead of once an
rem hour. Run (or let the Wednesday task run) at ~10:27am ET so the 10:30am inventory
rem number is caught as the strips reprice. Public API polling only - same code, same
rem caps, same KILL switch; just a faster clock inside the one window a week it matters.
call "%~dp0_env.bat"
cd /d "%OILX_DIR%"
if not exist "%PY%" (
    echo [%date% %time%] venv missing - run scripts\1_setup.bat once first >> "%OILX_DIR%\data\out\auto_run_log.txt"
    exit /b 1
)
echo. >> "%OILX_DIR%\data\out\auto_run_log.txt"
echo ===== EIA BURST %date% %time% ===== >> "%OILX_DIR%\data\out\auto_run_log.txt"
"%PY%" -m oilx burst --minutes 70 --interval 120 >> "%OILX_DIR%\data\out\auto_run_log.txt" 2>&1
"%PY%" -m oilx equity-pick >> "%OILX_DIR%\data\out\auto_run_log.txt" 2>&1
exit /b 0

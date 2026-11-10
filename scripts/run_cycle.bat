@echo off
rem One unattended cycle: scan Kalshi's WTI markets, then place capped demo orders for
rem clean signals. No pauses - this is what the scheduled task runs. All output is
rem appended to data\out\auto_run_log.txt.
call "%~dp0_env.bat"
cd /d "%OILX_DIR%"
if not exist "%PY%" (
    echo [%date% %time%] venv missing - run scripts\1_setup.bat once first >> "%OILX_DIR%\data\out\auto_run_log.txt"
    exit /b 1
)
echo. >> "%OILX_DIR%\data\out\auto_run_log.txt"
echo ===== cycle %date% %time% ===== >> "%OILX_DIR%\data\out\auto_run_log.txt"
"%PY%" -m oilx kalshi-scan >> "%OILX_DIR%\data\out\auto_run_log.txt" 2>&1
"%PY%" -m oilx kalshi-demo >> "%OILX_DIR%\data\out\auto_run_log.txt" 2>&1
"%PY%" -m oilx equity-pick >> "%OILX_DIR%\data\out\auto_run_log.txt" 2>&1
exit /b 0

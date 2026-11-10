@echo off
rem Turns the demo trader from "armed" to "hunting": registers a Windows scheduled task
rem that runs one scan+demo-order cycle every hour while this PC is on.
rem This file exists because Aria explicitly asked for the switch (2026-10-16); running it
rem is the owner's deliberate act. Turn off anytime with 9_autotrade_off.bat.
set TASKNAME=oilx demo trader
schtasks /Create /F /SC HOURLY /TN "%TASKNAME%" /TR "cmd /c \"\"%~dp0run_cycle.bat\"\""
if %errorlevel%==0 (
    echo.
    echo HUNTING: "%TASKNAME%" runs one cycle per hour while this PC is on.
    echo   Watch:  data\out\auto_run_log.txt  and  kalshi_demo_log.txt
    echo   Caps per cycle: 5 orders, 10 contracts each, 100 open max, demo exchange only.
    echo Running the first cycle now...
    schtasks /Run /TN "%TASKNAME%"
) else (
    echo Could not register the task. Fallback: open Command Prompt and paste the
    echo one-line schtasks command from the README.
)
pause

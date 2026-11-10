@echo off
schtasks /Delete /F /TN "oilx demo trader"
echo The hourly demo-trader task is removed. Back to "armed": nothing runs on its own.
pause

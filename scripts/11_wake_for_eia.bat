@echo off
rem Fixes the slept-through-the-EIA problem (Wed 2026-10-21):
rem  1. The existing hourly "oilx demo trader" task gets WakeToRun + run-on-battery +
rem     catch-up-if-missed settings.
rem  2. A new "oilx eia wednesday" task fires Wednesdays 10:27am ET, wakes the PC, and
rem     runs BURST mode (12_eia_burst.bat): scan+trade every 2 minutes for 70 minutes,
rem     so the 10:30am report is caught as the strips reprice - not an hour later.
rem Note: wake-from-sleep needs wake timers allowed (Power Options > Sleep > Allow wake
rem timers) and does not work from full shutdown or, on many laptops, with the lid shut.
rem The robust habit stays: Wednesday mornings, plugged in and awake.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$s = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable;" ^
 "try { Set-ScheduledTask -TaskName 'oilx demo trader' -Settings $s | Out-Null; Write-Host 'hourly task: wake+battery+catchup settings applied' } catch { Write-Host ('hourly task not found - run 8_autotrade_on.bat first: ' + $_) };" ^
 "$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"\"' + '%~dp012_eia_burst.bat' + '\"\"');" ^
 "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At 10:27;" ^
 "Register-ScheduledTask -TaskName 'oilx eia wednesday' -Action $a -Trigger $t -Settings $s -Force | Out-Null;" ^
 "Write-Host 'Wednesday 10:27am EIA burst registered (wakes the PC if asleep).'"
pause

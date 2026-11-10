@echo off
rem Shared environment for oilx scripts. Venv lives outside OneDrive (pmx lesson:
rem OneDrive syncing thousands of package files is misery).
set OILX_DIR=%~dp0..
set VENV=%LOCALAPPDATA%\oilx-venv
set PY=%VENV%\Scripts\python.exe

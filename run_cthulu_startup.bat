@echo off
REM Startup script to launch Cthulu at boot using the project venv Python
SET CT_DIR=C:\workspace\cthulu
SET PY="C:\workspace\cthulu\.venv\Scripts\python.exe"
SET CONFIG=%CT_DIR%\config.json
SET LOG=%CT_DIR%\logs\Cthulu_startup.log






REM Start Cthulu minimized in background; append stdout/stderr to logfile
REM Ensure logs directory exists
if not exist "%CT_DIR%\logs" mkdir "%CT_DIR%\logs"

REM Start Cthulu minimized in background; append stdout/stderr to logfile
START "Cthulu" /MIN "%PY%" -m cthulu --config "%CONFIG%" --skip-setup >> "%LOG%" 2>&1

exit /b 0

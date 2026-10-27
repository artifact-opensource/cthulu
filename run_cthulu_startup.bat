@echo off
setlocal
for %%I in ("%~dp0.") do set "CT_DIR=%%~fI"
set "PY=%CT_DIR%\.venv\Scripts\python.exe"
set "CONFIG=%CT_DIR%\config.json"
set "LOG=%CT_DIR%\logs\Cthulu_startup.log"
set "PYTHONIOENCODING=utf-8"

if not exist "%PY%" (
    echo [cthulu] Project virtualenv Python not found: "%PY%"
    exit /b 1
)
if not exist "%CONFIG%" (
    echo [cthulu] Configuration not found: "%CONFIG%"
    exit /b 1
)
if not exist "%CT_DIR%\logs" mkdir "%CT_DIR%\logs"

powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%CT_DIR%\run_cthulu_startup.ps1"
if errorlevel 1 (
    echo [cthulu] Previous instance cleanup failed; refusing to start another instance.
    exit /b 1
)

start "Cthulu" /MIN /D "%CT_DIR%" "%PY%" -u -m cthulu --config "%CONFIG%" --skip-setup --mindset ultra_aggressive >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [cthulu] Failed to start the engine. Check "%LOG%".
    exit /b 1
)

exit /b 0

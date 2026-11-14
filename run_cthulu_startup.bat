@echo off
setlocal
for %%I in ("%~dp0.") do set "CT_DIR=%%~fI"

echo [cthulu] Preparing the Python environment and dependencies...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CT_DIR%\scripts\setup.ps1" -ForLauncher
if errorlevel 1 goto setup_failed

choice /C KALX /N /M "Choose action: [K]ill and stay down, [A]gentic, [L]egacy, e[X]it: "
if errorlevel 4 exit /b 0
if errorlevel 3 (
    set "MODE=legacy"
    goto mode_selected
)
if errorlevel 2 (
    set "MODE=agentic"
    goto mode_selected
)
if errorlevel 1 goto killswitch

:mode_selected
choice /C SMHX /N /M "Choose trading mode: [S]ingle, [M]ulti, [H]FT, e[X]it: "
if errorlevel 4 exit /b 0
if errorlevel 3 goto hft
if errorlevel 2 set "CONFIG=config_multi.json"
if errorlevel 1 if not defined CONFIG set "CONFIG=config.json"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CT_DIR%\run_cthulu_startup.ps1" -Mode "%MODE%" -Config "%CONFIG%" -Resume
if errorlevel 1 (
    echo [cthulu] Startup failed. Check the latest logs in "%CT_DIR%\logs".
    pause
    exit /b 1
)

exit /b 0

:setup_failed
echo [cthulu] Setup failed. Trading startup is disabled until the error above is resolved.
choice /C KX /N /M "Choose action: [K]ill and stay down, e[X]it: "
if errorlevel 2 exit /b 1
if errorlevel 1 goto killswitch
exit /b 1

:hft
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CT_DIR%\run_cthulu_hft_startup.ps1" -Mode "%MODE%" -Resume
if errorlevel 1 (
    echo [cthulu] HFT startup failed or was blocked by preflight. Check the latest logs in "%CT_DIR%\logs".
    pause
    exit /b 1
)

exit /b 0

:killswitch
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CT_DIR%\cthulu_killswitch.ps1"
if errorlevel 1 (
    echo [cthulu] Kill switch did not complete. Run this launcher as Administrator if access is denied.
    pause
    exit /b 1
)
exit /b 0

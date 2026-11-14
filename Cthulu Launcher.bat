@echo off
setlocal
for %%I in ("%~dp0.") do set "CT_DIR=%%~fI"

if not exist "%CT_DIR%\run_cthulu_startup.bat" (
    echo [cthulu] Could not find run_cthulu_startup.bat next to this launcher.
    pause
    exit /b 1
)

call "%CT_DIR%\run_cthulu_startup.bat"
exit /b %errorlevel%

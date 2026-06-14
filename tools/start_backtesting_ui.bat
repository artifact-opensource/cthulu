@echo off
REM Cthulu Backtesting UI - Quick Start Script
REM Activates integration and starts backend

echo ================================================================================
echo CTHULU BACKTESTING UI - QUICK START
echo ================================================================================
echo.

echo Step 1: Activating UI Integration...
REM python scripts\activate_ui_integration.py
REM if errorlevel 1 (
REM     echo.
REM     echo ERROR: Failed to activate integration
REM     pause
REM     exit /b 1
REM )
echo [Skipped - Script not found]

echo.
echo Step 2: Starting Backend Server...
echo.
echo Backend will start on http://127.0.0.1:5000
echo Press Ctrl+C to stop the server
echo.
REM Open UI in 3 seconds...
timeout /t 3 /nobreak >nul

REM Start backend in background
start "Cthulu Backend" python backtesting\ui_server.py

echo.
echo Waiting for backend server to be ready...
:check_backend
curl -s http://127.0.0.1:5000/api/health >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    set /a retry_count+=1
    if %retry_count% lss 30 goto check_backend
    echo.
    echo ERROR: Backend failed to start in time.
    pause
    exit /b 1
)

echo Backend is READY!
echo.

REM Open UI in default browser
start backtesting\ui\index.html

echo.
echo ================================================================================
echo UI opened in browser!
echo Backend running in separate window
echo.
echo Look for the green "Backend Connected" indicator in the top-right
echo.
echo To stop:
echo   - Close this window
echo   - Close the "Cthulu Backend" window
echo ================================================================================
echo.

pause

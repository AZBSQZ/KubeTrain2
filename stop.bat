@echo off
title KubeTrain2 Stop

echo ========================================
echo   KubeTrain2 System Stop
echo ========================================
echo.

echo [1/2] Stopping backend service (port 8010)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8010" ^| findstr "LISTENING" 2^>nul') do (
    echo   Killing process PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [2/2] Stopping frontend service (port 5173)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING" 2^>nul') do (
    echo   Killing process PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Closing related windows...
taskkill /FI "WINDOWTITLE eq KubeTrain2*" /F >nul 2>&1

echo.
echo ========================================
echo   KubeTrain2 Stopped
echo ========================================
echo.
echo Press any key to close this window...
pause >nul

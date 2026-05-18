@echo off
title KubeTrain2 Startup

echo ========================================
echo   KubeTrain2 System Startup
echo ========================================
echo.

cd /d %~dp0

echo [Check] Python environment...
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Conda not found. Please install or initialize Anaconda/Miniconda
    echo.
    pause
    exit /b 1
)
conda run -n bs python --version

echo [Check] Node.js environment...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Please install Node.js 16+
    echo.
    pause
    exit /b 1
)
node --version
echo.

echo [1/2] Starting backend service (port 8010)...
cd backend
start "KubeTrain2-Backend" cmd /k "title KubeTrain2 Backend && conda run -n bs python run.py"
cd ..
echo   Backend window started

echo   Waiting for backend initialization...
timeout /t 3 /nobreak >nul

echo [2/2] Starting frontend service (port 5173)...
cd frontend
start "KubeTrain2-Frontend" cmd /k "title KubeTrain2 Frontend && npm run dev"
cd ..
echo   Frontend window started

echo.
echo ========================================
echo   KubeTrain2 Started!
echo   Backend: http://localhost:8010
echo   Frontend: http://localhost:5173
echo ========================================
echo.
echo NOTE: Backend and frontend run in separate windows.
echo       Do NOT close those windows or services will stop.
echo.
echo Press any key to open browser...
pause >nul
start http://localhost:5173
echo.
echo You can close this window now. Services will keep running.
pause

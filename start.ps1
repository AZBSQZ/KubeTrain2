# KubeTrain 2.0 启动脚本 (Windows PowerShell)
# 用法: .\start.ps1 [-Backend] [-Frontend] [-All]
param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$All
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"

function Start-Backend {
    Write-Host "[KubeTrain2] 启动后端 (port 8010)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$BackendDir'; conda run -n bs python run.py"
    ) -WindowStyle Normal
    Write-Host "[KubeTrain2] 后端进程已启动" -ForegroundColor Green
}

function Start-Frontend {
    Write-Host "[KubeTrain2] 安装前端依赖..." -ForegroundColor Cyan
    & npm install --prefix $FrontendDir
    Write-Host "[KubeTrain2] 启动前端开发服务器 (port 5173)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$FrontendDir'; npm run dev"
    ) -WindowStyle Normal
    Write-Host "[KubeTrain2] 前端进程已启动" -ForegroundColor Green
}

function Init-DB {
    Write-Host "[KubeTrain2] 初始化数据库..." -ForegroundColor Cyan
    $SqlFile = Join-Path $Root "kubetrain2.sql"
    Write-Host "  请手动执行: mysql -u root -p kubetrain2 < $SqlFile" -ForegroundColor Yellow
    Write-Host "  或: CREATE DATABASE kubetrain2; USE kubetrain2; SOURCE $SqlFile;" -ForegroundColor Yellow
}

if ($All -or (-not $Backend -and -not $Frontend)) {
    Init-DB
    Start-Backend
    Start-Sleep -Seconds 3
    Start-Frontend
} elseif ($Backend) {
    Start-Backend
} elseif ($Frontend) {
    Start-Frontend
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  KubeTrain 2.0 启动完成" -ForegroundColor Magenta
Write-Host "  后端 API:    http://localhost:8010/api" -ForegroundColor Magenta
Write-Host "  前端 UI:     http://localhost:5173" -ForegroundColor Magenta
Write-Host "  默认账号:    admin / admin123" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta

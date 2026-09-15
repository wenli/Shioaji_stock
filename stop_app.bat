@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 切換至腳本所在目錄
cd /d "%~dp0"

title Stop Shioaji Stock Server
color 0E

echo ====================================================================
echo   [STOP] Shioaji Stock 伺服器停止腳本
echo ====================================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8001 .*LISTENING"') do (
    set PID=%%a
    set FOUND=1
    echo [關閉] 偵測到 Port 8001 執行中進程 [PID: !PID!]，正在停止...
    taskkill /F /PID !PID! >nul 2>&1
    if errorlevel 1 (
        echo [警告] 無法強制關閉 PID !PID!，可能需要以管理員權限執行。
    ) else (
        echo [成功] 已成功停止伺服器進程 [PID: !PID!]。
    )
)

if "!FOUND!"=="0" (
    echo [提示] 目前沒有偵測到佔用 Port 8001 的伺服器進程。
)

echo.
echo 視窗將在 2 秒後自動關閉...
ping 127.0.0.1 -n 3 >nul

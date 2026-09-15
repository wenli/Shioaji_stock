@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 切換至腳本所在目錄
cd /d "%~dp0"

title Shioaji Stock Quant Workstation
color 0A

echo ====================================================================
echo   [START] Shioaji Stock 台股願望清單與多策略量化回測工作站
echo ====================================================================
echo.

REM 1. 虛擬環境自動偵測與啟用
if exist "%~dp0.venv\Scripts\activate.bat" (
    echo [資訊] 偵測到專案虛擬環境 [.venv]，正在啟用...
    call "%~dp0.venv\Scripts\activate.bat"
) else if exist "%~dp0venv\Scripts\activate.bat" (
    echo [資訊] 偵測到專案虛擬環境 [venv]，正在啟用...
    call "%~dp0venv\Scripts\activate.bat"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        color 0C
        echo [錯誤] 系統未安裝 Python 或未加入 PATH 環境變數！
        echo 請先安裝 Python 3.10+ 並勾選 Add Python to PATH。
        echo.
        pause
        exit /b 1
    )
)

REM 2. 檢查 Port 8001 是否已經在運行
netstat -ano | findstr /R /C:":8001 .*LISTENING" >nul 2>&1
if "%errorlevel%"=="0" (
    echo [提示] 伺服器已在運行中 [Port 8001 已就緒]。
    echo [啟動] 正在為您開啟瀏覽器首頁: http://127.0.0.1:8001
    start http://127.0.0.1:8001
    echo.
    echo 視窗將在 3 秒後自動關閉...
    ping 127.0.0.1 -n 4 >nul
    exit /b 0
)

REM 3. 準備啟動服務
echo [啟動] 正在啟動 FastAPI 後端伺服器 [Port 8001]...
echo [定時] APScheduler 排程已設定：週一至週五 13:40 自動定時同步
echo [提示] 伺服器啟動完成後將自動在瀏覽器中開啟首頁。
echo [提示] 如需停止服務，可直接關閉此視窗或按下 Ctrl + C。
echo.

REM 4. 背景異步倒數 2 秒後自動喚醒瀏覽器
start "" cmd /c "ping 127.0.0.1 -n 3 >nul & start http://127.0.0.1:8001"

REM 5. 啟動主程式
python app/main.py

if errorlevel 1 (
    echo.
    color 0C
    echo [錯誤] 伺服器異常終止，請檢查上方錯誤訊息或 .env 設定檔。
    echo.
    pause
)

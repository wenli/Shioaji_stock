import os
import sys
import time
import socket
import webbrowser
import threading

PORT = 8001
HOST = "127.0.0.1"
URL = f"http://{HOST}:{PORT}"

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, port)) == 0

def launch_browser():
    time.sleep(1.8)
    try:
        webbrowser.open(URL)
    except Exception as e:
        print(f"[警告] 自動開啟瀏覽器失敗: {e}")

def main():
    print("=" * 68)
    print("  🚀 Shioaji Stock 台股願望清單與多策略量化回測工作站")
    print("=" * 68)
    print()

    if is_port_in_use(PORT):
        print(f"[*] 提示：伺服器已在運行中（Port {PORT} 已就緒）。")
        print(f"[*] 啟動：正在為您開啟瀏覽器首頁：{URL}")
        webbrowser.open(URL)
        print("\n視窗將在 3 秒後自動關閉...")
        time.sleep(3)
        sys.exit(0)

    print(f"[*] 啟動：正在啟動 FastAPI 後端伺服器 (Port {PORT})...")
    print("[*] 定時：APScheduler 排程已設定：週一至週五 13:40 自動定時同步")
    print(f"[*] 提示：伺服器啟動完成後將自動在瀏覽器中開啟首頁：{URL}")
    print("[*] 提示：如需停止服務，可直接關閉此終端視窗或按下 Ctrl + C。\n")

    # 啟動非同步開圖執行緒
    browser_thread = threading.Thread(target=launch_browser, daemon=True)
    browser_thread.start()

    # 啟動主服務
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)

if __name__ == "__main__":
    main()

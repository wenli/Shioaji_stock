import os
import sys
import time
import subprocess

PORT = "8001"

def stop_server():
    print("=" * 68)
    print("  🛑 Shioaji Stock 伺服器停止腳本")
    print("=" * 68)
    print()

    try:
        out = subprocess.check_output("netstat -ano", shell=True, text=True)
    except Exception as e:
        print(f"[錯誤] 無法執行 netstat 查詢: {e}")
        return

    pids = set()
    for line in out.splitlines():
        line = line.strip()
        if f":{PORT}" in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                pids.add(parts[-1])

    if pids:
        for pid in pids:
            print(f"[關閉] 偵測到 Port {PORT} 執行中進程 [PID: {pid}]，正在停止...")
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        print("\n[成功] 已成功停止伺服器進程。")
    else:
        print(f"[提示] 目前沒有偵測到佔用 Port {PORT} 的伺服器進程。")

    print("\n視窗將在 2 秒後自動關閉...")
    time.sleep(2)

if __name__ == "__main__":
    stop_server()

# Shioaji Stock Wish List Updater — 設計與架構說明書

本文件紀錄了 **Shioaji Stock Wish List Updater (台灣股票願望清單自動更新系統)** 的核心需求、架構設計、邊界處理與開發決策。

---

## 🎯 產品定義 (Product Definition)

本專案旨在提供一個個人化的台灣股票數據收集與監控面盤。用戶可以透過美觀的網頁面盤管理自己的願望股票清單，系統會自動且高效率地在背景同步並聚合這些股票的各週期 K 線數據，以作為未來策略分析與回測的本地數據庫。

### 核心功能 (Core Features)
1. **股票清單管理 (Wish List CRUD)**：支援在 Web 前端動態新增、刪除追蹤的股票。
2. **斷點續傳數據同步 (Smart Sync)**：自動查詢資料庫中該股最後 timestamp，僅下載其後之新 K 線數據。
3. **多時區記憶體聚合 (Pandas Resample)**：從 Shioaji 下載 1 分 K (1k) 後，自動在記憶體端聚合出 5k, 15k, 30k, 60k, 1d 各週期並寫入資料庫。
4. **Glassmorphic 霓虹風 Dashboard**：提供極具質感的暗黑磨砂玻璃面盤，展示股票清單、最新股價/漲跌幅、各週期更新進度。
5. **歷史 K 線查看彈窗 (Lightweight-Charts Modal)**：點擊任一股票，於 Modal 燈箱中展示 Lightweight-Charts 歷史 K 線圖，並支援 1k/5k/1d 等週期的快速切換。

---

## ⚙️ 核心假設與限制 (Assumptions & Constraints)

1. **憑證依賴**：必須在 `.env` 中提供有效的 Shioaji API Key 與 Secret Key。
2. **1 分 K 歷史長度**：Shioaji API 下載股票 1 分 K 通常有 30-45 天的歷史限制。
3. **新增股票預設回溯**：若資料庫中無歷史資料，預設下載天數由 `.env` 中的 `DEFAULT_START_DAYS`（預設為 30 天）控制。
4. **自動排程時間**：每日排程定於台股收盤後（週一至週五 13:40）執行，以避開交易時間並取得完整當日數據。
5. **冷卻延遲**：下載多檔股票時，兩者之間加入 `1.5 秒` 的冷卻時間，防範 API 頻率限制。

---

## 🏗️ 系統架構與元件設計 (System Architecture)

專案採用 **FastAPI + SQLite + APScheduler** 的一體化輕量架構（方案一）。所有服務運行於單一 Python 進程中，結構如下：

```
c:\Intel\Shioaji_stock\
├── app/
│   └── main.py              # FastAPI 服務入口、Web APIs、APScheduler 排程註冊
├── download_stock_data.py   # 股票合約檢索、1k歷史下載、Resample 聚合與 SQLite 寫入
├── scheduler_manager.py     # APScheduler 背景排程管理 (週一至週五 13:40 觸發)
├── frontend/
│   └── index.html           # 暗黑玻璃霓虹風 Dashboard SPA (含 Lightweight-Charts K線彈窗)
├── scratch/
│   └── test_stock_sync.py   # 獨立核心下載與聚合功能測試腳本
├── .env                     # 環境變數與 Shioaji 金鑰
├── Shioaji.db               # SQLite 資料庫 (儲存 wish_list 與 K線表格)
└── requirements.txt         # 專案套件依賴
```

---

## 🗄️ 資料庫 Schema 設計 (Database Schema)

### 1. `wish_list` 資料表
```sql
CREATE TABLE IF NOT EXISTS wish_list (
    code TEXT PRIMARY KEY,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active',
    last_sync_ts TIMESTAMP
);
```

### 2. K 線數據表 (`stock1k`, `stock5k`, `stock15k`, `stock30k`, `stock60k`, `stock1d`)
```sql
-- 每個週期的表格結構均相同
CREATE TABLE IF NOT EXISTS stock1k (
    code TEXT,
    ts TIMESTAMP,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    PRIMARY KEY (code, ts)
);
```

---

## 📝 決策日誌 (Decision Log)

| 決策項目 | 採行方案 | 曾考慮之替代方案 | 採行原因 |
| :--- | :--- | :--- | :--- |
| **願望清單管理方式** | **SQLite + Web 前端 UI** | 寫死於 `.env` 中 (e.g. `WISH_LIST=2330,2454`) | 提供更友善、直觀的互動介面，方便用戶動態增刪股票而無需重啟服務或編輯程式碼。 |
| **數據精確度與週期** | **下載 1 分 K 並多週期聚合** | 僅下載日 K 線 (Daily K-bars) | 雖然日 K 下載極快，但為日後進行日內高頻策略回測或精細技術指標分析保留了完整的數據厚度。 |
| **圖表實時性設計** | **點擊彈窗靜態歷史查看** | WebSocket 實時 Tick 串流看盤 | 股票願望清單以「歷史數據累積與分析」為重。使用靜態加載能避免大量股票 Tick 訂閱造成的頻率限制，降低 CPU 與網路開銷，穩定度更高。 |
| **併發調度方案** | **FastAPI + BackgroundTasks** | Celery + Redis 異步任務佇列 | 對於 10~50 檔股票的個人清單，一體化背景排程已綽綽有餘。Celery/Redis 會大幅增加 Windows 環境的部署與運維複雜度，違反 YAGNI 原則。 |

---

## 🛑 異常與邊界處理 (Error & Edge Cases)

1. **Shioaji 離線狀態**：若 API 登入失敗，FastAPI 會啟動但將系統狀態標記為 `Offline`，前端會呈現醒目警告並禁用所有增刪、同步操作。
2. **無效代碼攔截**：新增股票時，後端會利用 `api.Contracts.Stocks` 檢索。若不存在，直接拋出 `400 Bad Request`，並由前端 Toast 提示用戶。
3. **無交易數據跳過**：當排程或手動同步在非交易日執行時，若 API 回傳空 K 線，後端會安全地跳過寫入，不拋出錯誤。
4. **SQLite 鎖定防範**：資料庫連線開啟 `timeout=30.0`，確保背景同步與前端查詢不發生寫入衝突。

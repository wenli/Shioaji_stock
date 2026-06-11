# Shioaji Stock Wish List Updater (台股願望清單多週期自動更新器)

參考 `Shioaji_job` 的一體式輕量架構，專為台灣股票市場設計的願望清單管理、背景定時 K 線下載與多週期自動聚合系統。

搭配高質感的磨砂玻璃 (Glassmorphic) 暗黑霓虹風 Web 控制面盤，並整合 Lightweight-Charts 歷史 K 線互動看盤彈窗。

---

## 🌟 特色功能

1. **📊 股票願望清單管理 (Wish List CRUD)**
   * 提供前端 Web 介面，支援動態輸入代碼新增與移出追蹤股票。
   * 新增股票時會透過 Shioaji 自動查詢股票名稱（如 `2330` 自動補完 `台積電`）並寫入 SQLite 資料庫。

2. **⚡ 智慧斷點續傳數據同步 (Smart Sync & Cooldown)**
   * 下載時自動查詢資料庫中該股最後一筆 `ts` 時間戳，僅下載該時間點之後的新數據，避免重複抓取與浪費 API 額度。
   * 下載多檔股票時，自動在股票之間加入 **1.5 秒的冷卻延遲**，以防範觸發 Shioaji 的 API 頻率限制 (Rate Limit)。

3. **🗂️ 內存多週期自動聚合 (Resample)**
   * 原生下載 Shioaji 股票最細顆粒度的 **1K** 數據。
   * 自動在內存端使用 Pandas 對齊聚合為：**5K, 15K, 30K, 60K, 1D** 各週期並分別寫入對應的資料表中。
   * 因台股無夜盤，聚合邏輯更為簡潔且性能更佳。

4. **📅 自動排程與手動一鍵同步**
   * 整合 `APScheduler` 背景排程管理，**週一至週五 13:40** (台股收盤後) 自動在背景執行一鍵同步，自動補齊所有追蹤股票當日最新行情。
   * 提供前端面盤一鍵手動同步按鈕，可異步喚醒背景同步。

5. **📈 Lightweight-Charts 歷史看盤彈窗**
   * 點擊追蹤表格中的股票，立即彈出 Modal，以 TradingView 的 `lightweight-charts` 渲染歷史線圖。
   * 支援在彈窗內快速切換 **1m, 5m, 15m, 30m, 60m, 1d** 各個週期。
   * 鎖定 Lightweight Charts 4.2.3 穩定版 CDN 連結以確保最佳相容性。

---

## 🏗️ 專案目錄結構

```
c:\Intel\Shioaji_stock\
├── app/
│   └── main.py              # FastAPI 服務入口、Web APIs、APScheduler 生命週期
├── frontend/
│   ├── index.html           # 磨砂玻璃霓虹風 Dashboard SPA (含 Lightweight-Charts 彈窗)
│   └── lightweight-charts.standalone.production.js # 本地備份圖表庫 (可替換 CDN)
├── scratch/
│   └── test_stock_sync.py   # 獨立核心下載與聚合管道測試驗證腳本
├── .env                     # 環境變數與 Shioaji 金鑰
├── Shioaji.db               # SQLite 資料庫 (自動建立)
├── requirements.txt         # 專案套件依賴
└── README.md                # 本說明文件
```

---

## ⚙️ 安裝與設定環境

### 1. 安裝套件依賴
建議在專案目錄下使用您的 Python 環境安裝依賴：
```bash
pip install -r requirements.txt
```

### 2. 配置環境變數 `.env`
於專案根目錄下建立 `.env` 檔案，配置您的 Shioaji 憑證與起始下載範圍：

```env
# Shioaji API 帳號與密鑰
SHIOAJI_API_KEY="您的_shioaji_api_key"
SHIOAJI_SECRET_KEY="您的_shioaji_secret_key"

# 模擬(simulation)或實盤(production)模式
SHIOAJI_ENV="simulation"

# 預設資料庫 (SQLite) 名稱
DB_NAME="Shioaji.db"

# 當新增一檔全新股票且資料表全空時，預設向前回溯下載的天數 (預設 30 天，可設至 180 天)
DEFAULT_START_DAYS=30
```

---

## 🚀 啟動方式

確保 `.env` 配置正確後，執行主入口腳本：

```bash
python app/main.py
```

* **Web 面盤網址**: **`http://127.0.0.1:8001/`**
  * *註：為避免與 `Shioaji_job` (Port 8000) 衝突，本股票專案之連接埠已預設修改為 `8001`。可隨時在 `app/main.py` 底部的 `port=8001` 進行修改。*

---

## 🗄️ 資料庫 Schema 說明

資料庫 `Shioaji.db` 在服務初次啟動時會自動完成初始化與表格建立。

### 1. 願望清單表 `wish_list`
| 欄位名 | 類型 | 說明 |
| :--- | :--- | :--- |
| `code` | TEXT (PK) | 股票代碼 (如 `2330`) |
| `name` | TEXT | 股票名稱 (如 `台積電`) |
| `created_at` | TIMESTAMP | 新增至清單的時間 |
| `status` | TEXT | 同步狀態 (`active` / `paused`) |
| `last_sync_ts` | TIMESTAMP | 上次成功同步 1K 的最新時間戳 |

### 2. 各週期 K 線數據表 (`stock1k`, `stock5k`, `stock15k`, `stock30k`, `stock60k`, `stock1d`)
各週期表格欄位皆一致：
* `code` (TEXT) - 股票代碼
* `ts` (TIMESTAMP) - K 線時間戳（格式如 `YYYY-MM-DD HH:MM:SS`）
* `open` / `high` / `low` / `close` (REAL) - 開高低收點位
* `volume` (INTEGER) - 該根 K 棒的累積成交張數 / 股數
* **聯合主鍵**：`PRIMARY KEY (code, ts)`

---

## 🔗 APIs 端點參考

| 方法 | 端點 | 說明 |
| :--- | :--- | :--- |
| `GET` | `/` | 渲染 Web Dashboard 首頁 UI |
| `GET` | `/api/status` | 讀取 Shioaji 連線狀態 (Connected / Offline) |
| `GET` | `/api/wishlist` | 獲取清單中所有股票狀態、最新收盤價/漲跌幅與各週期最後更新點 |
| `POST` | `/api/wishlist` | 新增股票代碼並於背景觸發該股歷史數據下載 |
| `DELETE` | `/api/wishlist/{code}`| 將股票自清單移除並清除其歷史 K 線資料 |
| `POST` | `/api/sync` | 背景手動觸發一鍵 Full-Sync 下載同步 (斷點續傳) |
| `GET` | `/api/kbars/{code}` | 讀取單檔股票特定週期歷史數據，提供前端 Lightweight-Charts 繪圖 |

---

## ⚠️ 疑難排解與注意事項

1. **Port 衝突**：若啟動時報錯 `[WinError 10013] 以一種被禁用的方式嘗試訪問通訊通訊端`，代表 `8001` 埠被其他程式佔用。請編輯 `app/main.py` 最底部的 `port=8001` 改為其他埠（如 `8080` 或 `8002`）。
2. **新增股票提示失敗**：請確認 Shioaji API 是否成功登入。若處於離線狀態（網頁頂部顯示紅色 `Offline/Unlogged`），則無法進行合約檢索，請檢查 `.env` 內 API 金鑰是否正確。
3. **無效代碼**：Shioaji 股票僅支援台股已上市/上櫃交易之代碼。若輸入不正確或已下市股票，後端會主動攔截並於前端彈出錯誤提示。

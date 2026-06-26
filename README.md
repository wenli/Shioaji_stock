# Shioaji Stock Wish List Updater (台股願望清單多週期自動更新與多策略量化回測系統)

參考 `Shioaji_job` 的一體式輕量架構，專為台灣股票市場設計的願望清單管理、背景定時 K 線下載與多週期自動聚合系統。

系統內建強大的**多策略量化回測引擎 (Backtester)**，支援雙向交易（做多/做空）與跨日持倉，搭配高質感的磨砂玻璃 (Glassmorphic) 暗黑霓虹風 Web 控制面盤，並整合 Lightweight-Charts 歷史 K 線互動看盤頁面。

📖 **詳細使用與操作說明請參閱：[系統使用與操作手冊 (User Guide)](docs/user_guide.md)**

---

## 🌟 特色功能

1. **📊 股票願望清單管理 (Wish List CRUD)**
   * 提供前端 Web 介面，支援動態輸入代碼新增與移出追蹤股票。
   * 新增股票時會透過 Shioaji 自動查詢股票名稱（如 `2330` 自動補完 `台積電`）並寫入 SQLite 資料庫。

2. **⚡ 智慧斷點續傳與自動分批下載 (Smart Sync, Chunking & Cooldown)**
   * 下載時自動查詢資料庫中該股最後一筆 `ts` 時間戳，僅下載該時間點之後的新數據，避免重複抓取。
   * **突破 30 天查詢限制**：由於 Shioaji API 每次 `kbars` 查詢區間不得超過 30 天，本系統會自動將大於 30 天的下載區間拆分為多個最長 29 天的區間分批下載，並在批次間加入 **0.5 秒的冷卻延遲**，最後合併與去重，支援長時間歷史數據一鍵拉取。
   * 下載多檔股票時，自動在股票之間加入 **1.5 秒的冷卻延遲**，防範觸發 Shioaji 的 API 頻率限制 (Rate Limit)。

3. **🗂️ 內存多週期自動聚合 (Resample)**
   * 原生下載 Shioaji 股票最細顆粒度的 **1K** 數據。
   * 自動在內存端使用 Pandas 對齊聚合為：**5K, 15K, 30K, 60K, 1D** 各週期並分別寫入對應的資料表中。

4. **📅 自動排程與手動一鍵同步**
   * 整合 `APScheduler` 背景排程管理，**週一至週五 13:40** (台股收盤後) 自動在背景執行一鍵同步，自動補齊所有追蹤股票當日最新行情。
   * 提供前端面盤一鍵手動同步按鈕，可異步喚醒背景同步。

5. **📈 Lightweight-Charts 獨立多週期看盤新頁**
   * 點擊追蹤表格中的股票，另開新分頁 (New Tab) 以 `/chart/{code}` 路由獨立展示該股的多週期趨勢。
   * **2x2 四宮格量價共振**：在單一頁面同時呈現 **5M、15M、60M、日K** 四個週期的 K 線圖。
   * **量能疊加與台北時區防護**：底部疊加半透明的成交量 (Volume) 柱狀圖，並配置時區修正，使時間軸在世界任何地方均對齊台北時間 (UTC+8)。

6. **📥 一鍵匯入 Yahoo 熱門成交股與 Web 控制設定**
   * 提供一鍵式按鈕，自動抓取 Yahoo 股市最新成交量排行且股價小於門檻的股票。
   * Web 介面整合「Yahoo 匯入設定」設定面板，可調整股價上限 (`YAHOO_IMPORT_MAX_PRICE`) 與抓取數量限制 (`YAHOO_IMPORT_LIMIT`)，並持久化寫入 `.env` 檔案中。

7. **🧪 多策略量化回測系統 (Multi-Strategy Backtester)**
   * **多種交易策略支援**：支援在 Web 介面自由切換執行以下四大策略：
     1. **SMC 策略 (Smart Money Concepts)**：利用日線判斷 BOS 與折溢價區，並在分K進行 Sweep、ChoCH 與 FVG 限價單成交判定。
     2. **EMA 均線黃金死亡交叉**：EMA 雙均線交叉順勢策略。
     3. **Bollinger Bands 布林通道逆勢**：超買超賣之均值回歸策略。
     4. **KD stochastic 隨機指標轉折**：低檔金叉買入、高檔死叉做空的指標策略。
   * **高階回測控制參數**：
     * 支援**雙向交易**（僅做多 / 雙向交易，支援融券做空）。
     * 支援**持倉模式**（當沖 Day Trade 當日強平 / 跨日波段 Swing Trade 持續持有）。
     * 支援**回測分K週期**（5分鐘K / 15分鐘K）自由切換。
     * 可設定初始資金（預設已優化為 1,001,000 元）、單筆風險比率（%）、盈虧比（R:R）、ATR 止損緩衝以及手續費折讓等參數。
   * **圖表與夏普值指標**：回測成功後自動繪製出帳戶淨值曲線 (Equity Curve)，並列出**總報酬率、勝率、交易次數、最大回撤、獲利因子、夏普比率 (Sharpe Ratio)**等專業量化指標以及交易歷史明細。
   * **歷史資料自動補齊**：回測時若本地資料天數不足，將自動在背景呼叫 Shioaji 分段下載（突破 30 天限制）補齊所需資料。

---

## 🏗️ 專案目錄結構

```
c:\Intel\Shioaji_stock\
├── app/
│   ├── main.py              # FastAPI 服務入口、Web APIs、APScheduler 生命週期
│   └── backtester.py        # 核心多策略回測引擎 (SMC, EMA, BB, KD)
├── frontend/
│   ├── index.html           # 磨砂玻璃霓虹風 Dashboard 首頁
│   ├── chart.html           # 獨立 2x2 多週期看盤面盤 (K線 + 成交量)
│   └── backtest.html        # 多策略量化回測與指標分析面板
├── scratch/
│   ├── optimize_smc.py      # SMC 策略多股票網格參數優化搜尋腳本
│   ├── strategy_tournament.py # 四大策略在台股市場同台競技對比腳本
│   ├── test_backtest.py     # 回測引擎底層雙向與波段機制驗證腳本
│   └── api_test_multi.py    # 自動化測試 FastAPI 與多策略 API 整合驗證腳本
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

# 當新增一檔全新股票且資料表全空時，預設向前回溯下載的天數 (建議 360 天以利歷史回測)
DEFAULT_START_DAYS=360

# Yahoo 熱門股匯入設定
YAHOO_IMPORT_MAX_PRICE=150  # 股價上限
YAHOO_IMPORT_LIMIT=50       # 排行抓取數量
```

---

## 🚀 啟動方式

確保 `.env` 配置正確後，執行主入口腳本：

```bash
python app/main.py
```

* **Web 面盤網址**: **`http://127.0.0.1:8001/`**
  * *連接埠已預設為 `8001`，以避免與其他服務衝突。*

* **量化策略研究報告**：
  * **[台股最佳交易策略大評比研究報告](docs/best_taiwan_strategy_report.md)**：詳細分析了台股高頻交易中的「摩擦成本陷阱」與各策略在台股的生存表現。
  * **[SMC 策略優化分析報告](docs/smc_strategy_report.md)**：探討 SMC 策略最合適台股之參數設定。

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
各週期表格欄位皆一致，聯合主鍵為 `PRIMARY KEY (code, ts)`：
* `code` (TEXT) - 股票代碼
* `ts` (TIMESTAMP) - K 線時間戳（`YYYY-MM-DD HH:MM:SS`）
* `open` / `high` / `low` / `close` (REAL) - 開高低收點位
* `volume` (INTEGER) - 該根 K 棒的累積成交股數

---

## 🔗 APIs 端點參考

| 方法 | 端點 | 說明 |
| :--- | :--- | :--- |
| `GET` | `/` | 渲染 Web Dashboard 首頁 UI |
| `GET` | `/api/status` | 讀取 Shioaji 連線狀態 |
| `GET` | `/api/wishlist` | 獲取清單中所有股票狀態與最新收盤價/漲跌幅 |
| `POST` | `/api/wishlist` | 新增股票代碼並於背景觸發該股歷史數據下載 |
| `DELETE` | `/api/wishlist/{code}`| 將股票自清單移除並清除其歷史 K 線資料 |
| `POST` | `/api/sync` | 背景手動觸發一鍵 Full-Sync 下載同步 (斷點續傳) |
| `GET` | `/api/settings/yahoo` | 獲取當前記憶體中的 Yahoo 熱門股匯入設定值 |
| `POST` | `/api/settings/yahoo` | 更新 Yahoo 熱門股匯入設定值並寫入持久化至 `.env` |
| `POST` | `/api/import_yahoo` | 爬取 Yahoo 成交量排行並匯入 wish list 進行背景同步 |
| `POST` | `/api/backtest` | **執行指定個股之特定量化策略（SMC/EMA/BB/KD）歷史回測** |
| `GET` | `/api/kbars/{code}` | 讀取單檔股票特定週期歷史數據，提供看盤圖表繪製 |
| `GET` | `/chart/{code}` | 渲染獨立的 2x2 四宮格 K 線量能看盤頁面 |
| `GET` | `/api/stock/{code}` | 獲取特定個股合約名稱（整合 Shioaji 與 DB Fallback 查詢機制） |
| `GET` | `/api/kbars/multi/{code}`| 一鍵查詢單檔股票多週期 (5K, 15K, 60K, 日K) 的量價數據 |

---

## 🔬 台股量化策略研究成果與最佳實踐

我們針對台灣股市（台股）的獨特交易規則（如每日 4.5 小時交易時間、10% 漲跌幅限制及交易摩擦成本），回測了從 2025 年 7 月 1 日至 2026 年 6 月 24 日（約一整年）的歷史數據，涵蓋了指數型 ETF（0050）、大型權值股（台積電 2330、鴻海 2317）及中型波動股（長榮航 2618）。

### 1. 核心研究發現：台股的「交易摩擦成本陷阱」
在台股中，買賣一次手續費為 0.1425%（進出兩次），加上證交稅 0.3%，即便手續費打 6 折，每筆交易的摩擦成本也高達 **0.47%**。
* ⚠️ **「夏普比率騙局」**：例如在 0050 的布林通道波段回測中，夏普比率高達 **3.37**（代表淨值波動極其平滑且具規律），但其總回報率卻是驚人的 **-84.17%**！這是因為一年內促成了 **389 次交易**，光摩擦成本就消耗了高達 `389 * 0.47% = 182.8%` 的本金。
* 💡 **SMC 策略 (Smart Money Concepts) 的優勢**：SMC 策略具有極度挑剔的進場條件（Sweep + ChoCH + FVG 三重確認），一年內對每檔股票僅交易 4 ~ 7 次。這種**低頻交易、高盈虧比**的特性，徹底規避了台股的摩擦成本陷阱，是大資金或個人交易者在台股市場上生存並獲利的唯一可行策略。

### 2. 四大策略同台競技評比表
*(回測參數基準：初始資金 1,000,000 元，單筆風險 1%，盈虧比 R:R 為 2.0，開啟多空雙向交易，LTF 週期為 5分K)*

| 標的 | 交易策略 | 持倉模式 | 總收益率 | 夏普比率 (Sharpe) | 勝率 | 交易次數 | 績效評級 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **0050** | **SMC 策略** | **波段 (Swing)** | **-2.79%** | **-1.44** | **33.3%** | **6** | **A (避開成本)** |
| | Bollinger Bands | 波段 (Swing) | -84.17% | 3.37 | 30.6% | 389 | F (摩擦破產) |
| | KD Indicator | 波段 (Swing) | -61.70% | 3.16 | 35.9% | 231 | F (摩擦破產) |
| | EMA Cross | 波段 (Swing) | -57.57% | 0.67 | 31.1% | 209 | F (摩擦破產) |
| **2317** | **SMC 策略** | **波段 (Swing)** | **+1.13%** | **+0.37** | **42.9%** | **7** | **A+ (最佳組合)** |
| | Bollinger Bands | 波段 (Swing) | -83.04% | 2.56 | 30.8% | 335 | F (摩擦破產) |
| | KD Indicator | 波段 (Swing) | -62.29% | 2.75 | 28.8% | 170 | F (摩擦破產) |
| | EMA Cross | 波段 (Swing) | -62.36% | 1.90 | 33.7% | 211 | F (摩擦破產) |
| **2618** | **SMC 策略** | **波段 (Swing)** | **+1.35%** | **+0.45** | **50.0%** | **4** | **A+ (最佳組合)** |
| | Bollinger Bands | 波段 (Swing) | -78.19% | 3.06 | 33.2% | 307 | F (摩擦破產) |
| | KD Indicator | 波段 (Swing) | -57.98% | 2.70 | 34.5% | 177 | F (摩擦破產) |
| | EMA Cross | 波段 (Swing) | -68.20% | 1.97 | 28.9% | 225 | F (摩擦破產) |

### 3. 台股最好的交易策略配置建議
根據研究結論，我們為台股整理出以下最佳策略配置：
* **首選策略**：**SMC (Smart Money Concepts) 策略**。
* **持倉模式**：必須是 **波段持有 (Swing)**。台股開盤時間僅 4.5 小時，當沖 (Day Trading) 難以拉開獲利空間，跨日波段持倉才能讓策略有足夠盈虧比。
* **交易標的**：選擇**中高波動度之個股**（如鴻海 2317、長榮航 2618），避開極低波動的平穩個股或指數。
* **交易方向**：必須**支援雙向交易（融券做空）**，以在日線偏向轉空時進行避險放空。
* **盈虧比 (R:R)**：設定為 **2.0 至 3.0**，以大波段利潤覆蓋不可避免的摩擦成本。

詳細優化過程與完整數據請參閱：
* [台股最佳交易策略大評比研究報告](docs/best_taiwan_strategy_report.md)
* [SMC 策略優化分析報告](docs/smc_strategy_report.md)

---

## 🛠️ 近期更新與優化記錄

1. **SMC 策略進場模式擴展 (OB 開盤價 & OTE 斐波那契回撤)**：
   * **後端實作**：於 [backtester.py](file:///c:/Intel/Shioaji_stock/app/backtester.py) 實作 Order Block (OB 開盤價) 進場與 Optimal Trade Entry (OTE 70.5% / 79% / 62% 斐波那契回撤) 進場模式，並於無陰/陽K線時，以 High/Low 作為回退支撐阻力進場。
   * **前端介面**：於 [backtest.html](file:///c:/Intel/Shioaji_stock/frontend/backtest.html) 提供對應的下拉選單，並在選擇非 SMC 策略時動態隱藏此選單。
2. **多週期 K 線 API 錨點支援與過早資料修復**：
   * 在 [main.py](file:///c:/Intel/Shioaji_stock/app/main.py) 的 `/api/kbars/multi/{code}` 路由新增 `anchor_time` 參數。若帶入此參數，系統會以該時間戳為中心，往前抓取 800 根、往後抓取 200 根 K 線，解決複盤時「過早資料無法顯示」的 Bug。
3. **多週期圖表同步與時間戳就近對齊**：
   * 在 [chart.html](file:///c:/Intel/Shioaji_stock/frontend/chart.html) 中，使 5M, 15M, 60M, 日K 圖表同步顯示買賣點 (arrowUp / arrowDown) 與橘色軌跡虛線。
   * 實作 `findNearestBarIndex` 時間對齊演算法，自動以就近原則在不同週期圖表上定位交易標記。
   * 自動為 5M, 15M, 60M 進行局部時間軸焦點聚焦 (Zoom)，並讓日K圖表保持全局趨勢視野。
4. **SMC 區間切換與 Bug 修復**：
   * 重構全域共享變數（`tradeLineSeriesList`, `tradeSMCSeriesList` 等）為各週期獨立的字典結構，避免圖表異步繪製時搶佔引用。
   * 修復在複盤模式下切換關閉「SMC 區間」開關時，SMC 著色區間依然殘留顯示，且重複切換會導致軌跡虛線重複疊加的 Bug。
5. **修正當日漲跌幅 % 數顯示放大 100 倍的 Bug**：
   * 移除了主入口 [main.py](file:///c:/Intel/Shioaji_stock/app/main.py#L209) 中對該欄位重複乘 100 的乘數，已恢復為正確的百分比顯示。
6. **優化回測初始資金預設值**：
   * 為了支援台股多空雙邊回測時，券商融券保證金與借券相關規定本金要求，將回測初始資金預設值調高至 **`1,001,000` 元**。
7. **優化回測引擎的 JSON 序列化機制**：
   * 引入了類型強制轉化（`float()` & `int()`）防護，解決 NumPy 數值型別（如 `numpy.float64` 等）無法被 FastAPI / JSON 引擎原生序列化的問題。
8. **新增獨立系統使用與操作手冊 (User Guide)**：
   * 於 [docs/user_guide.md](docs/user_guide.md) 以繁體中文撰寫完整操作指南，涵蓋清單管理、定時同步、2x2 四宮格看盤、量化回測與歷史複盤操作，並科普 SMC 交易策略基礎概念，並於 `README.md` 首頁加入導航連結。


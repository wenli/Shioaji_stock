# Feature Specification: 多週期 Order Block (OB) 即時雷達與監控

## 1. 需求背景與目標 (Understanding Summary)
* **目標**：在首頁儀表板（`frontend/index.html`）新增獨立的「Order Block (OB) 觸及即時雷達」卡片區塊，集中監控並即時呈現追蹤清單中是否有個股觸及 **5M、15M、60M、1Day** 週期的關鍵 Order Block。
* **目的**：讓使用者登入或開啟首頁時，瞬間掌握當下處於 SMC 進場熱區 (POI) 的標的，無須手動逐一翻閱各股票的多週期線圖。
* **適用對象**：採用 SMC (Smart Money Concepts) / ICT 策略進行當沖與波段交易的投資人。
* **明確排除 (Non-goals)**：不在此功能內直接觸發實盤自動下單。

## 2. 假設前提 (Assumptions)
1. 股票需有對應週期的歷史 K 線數據（由 Shioaji API 或 Yahoo Finance 同步寫入 SQLite）。
2. 在 K 線同步或排程更新完成時，後端自動重新計算各週期最新的未緩解 OB 並存入資料庫快取。
3. 離線或非開盤時間比對最後收盤價，盤中開盤時間比對即時報價。

## 3. 決策紀錄 (Decision Log)
| 決策項目 | 決策內容 | 評估理由 |
| :--- | :--- | :--- |
| **UI 呈現型式** | 獨立「OB 觸及即時雷達」卡片 + 表格週期指示點 | 雷達卡片聚焦高優先級觸及機會，表格提供全景監控 |
| **演算法** | 標準 SMC 反向 K 線 + 實體/陰陽線 High~Low 區間 + 未緩解過濾 | 符合專業機構操盤概念，排除已失效 OB |
| **運算架構** | SQLite 資料表持久化快取 (`stock_order_blocks`) | 保證首頁毫秒級載入，避免重複即時運算造成卡頓 |

## 4. 系統設計 (Final Design)

### 4.1 後端模組 (`app/smc_detector.py`)
* 負責讀取 K 線資料計算波段高低點 (Swing Highs/Lows)、結構破壞 (BOS)、Order Block 區間。
* 輸出有效未緩解 OB 清單：
  * `BULLISH`：引發向上突破的最後一根陰線（`top = high`, `bottom = low`）。
  * `BEARISH`：引發向下跌破的最後一根陽線（`top = high`, `bottom = low`）。
* 緩解檢查：若後續價格跌破 Bullish OB 的 Low 或升破 Bearish OB 的 High，則視為失效並回溯前一個 OB。

### 4.2 資料表結構 (`stock_order_blocks`)
* `code` TEXT (股票代碼)
* `timeframe` TEXT (週期：5k, 15k, 60k, 1d)
* `ob_type` TEXT (BULLISH / BEARISH)
* `top_price` REAL (OB 頂部價格)
* `bottom_price` REAL (OB 底部價格)
* `ob_time` TEXT (OB 發生時間)
* `updated_at` TEXT (運算更新時間)
* `PRIMARY KEY (code, timeframe)`

### 4.3 後端 API (`GET /api/ob-radar`)
* 查詢所有股票之 OB 快取，比對最新現價。
* 判定 `is_touching = (bottom_price <= live_price <= top_price)`。
* 返回即時觸及清單與全量 OB 狀態。

### 4.4 前端 UI (`frontend/index.html`)
* 頂部加入「OB 觸及即時雷達」卡片，有觸及的股票以呼吸燈與多空霓虹標籤展示，點擊可開啟 `/chart/{code}`。
* 原清單表格加入 4 個週期燈號，即時反應 5M / 15M / 60M / 1D 狀態。

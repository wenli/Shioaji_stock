# Feature Specification: 多週期 Order Block (OB) 即時雷達與監控（含進出場與停損目標規劃）

## 1. 需求背景與目標 (Understanding Summary)
* **目標**：在首頁儀表板（`frontend/index.html`）的「Order Block (OB) 觸及即時雷達」卡片中，集中監控個股觸及 **5M、15M、60M、1Day** 週期 OB 的狀態，並同步為各觸及週期提供即時的 **入場區間 (Entry)、停損價位 (SL)、目標出場價位 (TP1 1:2 / TP2 1:3) 與預估損益比 (R:R)**。
* **目的**：讓使用者登入或開啟首頁時，瞬間掌握當下處於 SMC 進場熱區 (POI) 的標的，並直接取得明確的風控與出場目標數值，無須手動換算損益比。
* **適用對象**：採用 SMC (Smart Money Concepts) / ICT 策略進行當沖與波段交易的投資人。
* **明確排除 (Non-goals)**：不在此功能內直接觸發實盤自動下單。

## 2. 假設前提 (Assumptions)
1. 股票需有對應週期的歷史 K 線數據（由 Shioaji API 或 Yahoo Finance 同步寫入 SQLite）。
2. 在 K 線同步或排程更新完成時，後端自動重新計算各週期最新的未緩解 OB 並存入資料庫快取。
3. 離線或非開盤時間比對最後收盤價，盤中開盤時間比對即時報價。
4. 進場中軸採用 OB 50%（Mean Threshold），多頭停損設於下緣略下方，空頭停損設於上緣略上方，目標分別以 1:2 (TP1) 與 1:3 (TP2) 計算。

## 3. 決策紀錄 (Decision Log)
| 決策項目 | 決策內容 | 評估理由 |
| :--- | :--- | :--- |
| **運算架構** | 後端統一計算附加 `trade_setup` 欄位 + 前端渲染 | 兼具擴展性（未來可直接複用於推播通知）與前端流暢性 |
| **UI 呈現型式** | 緊湊型雙層交易卡條（Compact Trade Spec Bar） | 保持卡片緊湊科技感，無須額外點擊即可一眼掌握全局數值 |
| **目標出場計算** | 標準 1:2 (TP1) & 1:3 (TP2) R:R 固定盈虧比模式 | 規則明確客觀，快速輔助評估風險報酬與風控決策 |
| **多週期處理** | 依各觸及週期獨立顯示該週期專屬交易規劃 | 讓當沖（5M/15M）與波段（60M/1D）各自有精準的對應目標 |

## 4. 系統設計 (Final Design)

### 4.1 交易規劃計算演算法 (`app/smc_detector.py` / `app/main.py`)
針對觸及的 Order Block（`bottom` ~ `top`）：
* **多頭 OB (Bullish Setup)**：
  * $Entry_{range} = [bottom, top]$
  * $Entry_{mid} = \frac{top + bottom}{2}$
  * $SL = bottom \times 0.995$（最低保護緩衝，風險空間 $Risk = Entry_{mid} - SL$）
  * $TP_1 = Entry_{mid} + (2 \times Risk)$（獲利率 $Gain\% = \frac{TP_1 - Entry_{mid}}{Entry_{mid}} \times 100\%$）
  * $TP_2 = Entry_{mid} + (3 \times Risk)$（獲利率 $Gain\% = \frac{TP_2 - Entry_{mid}}{Entry_{mid}} \times 100\%$）
* **空頭 OB (Bearish Setup)**：
  * $Entry_{range} = [bottom, top]$
  * $Entry_{mid} = \frac{top + bottom}{2}$
  * $SL = top \times 1.005$（最高保護緩衝，風險空間 $Risk = SL - Entry_{mid}$）
  * $TP_1 = Entry_{mid} - (2 \times Risk)$
  * $TP_2 = Entry_{mid} - (3 \times Risk)$

### 4.2 後端 API 回傳擴充 (`GET /api/ob-radar`)
在各週期的 OB 狀態字典中注入 `trade_setup` 物件：
```json
{
  "top": 105.0,
  "bottom": 100.0,
  "is_touching": true,
  "trade_setup": {
    "entry_range": [100.0, 105.0],
    "entry_mid": 102.5,
    "stop_loss": 99.5,
    "risk_pct": 2.93,
    "tp1": 108.5,
    "tp1_gain_pct": 5.85,
    "tp2": 111.5,
    "tp2_gain_pct": 8.78,
    "rr_label": "1:2 / 1:3"
  }
}
```

### 4.3 前端 UI 佈局升級 (`frontend/index.html`)
* 在 `.radar-item` 內各週期的 `.ob-chip` 中加入雙層結構：
  1. 上層：多空方向標籤與進場區間（`[bottom] ~ [top]`）
  2. 下層：3 個微型膠囊指標（`SL`、`TP1 (1:2)`、`TP2 (1:3)`），數值採用 monospace 字型精準對齊。
* 響應式優化：螢幕寬度縮小時自動換行，寬螢幕保持俐落橫排。

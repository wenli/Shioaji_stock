# 台股高勝率交易策略與極速特徵向量化回測引擎規格書
# (High-Winrate Taiwan Stock Strategy & Fast Vectorized Simulation Engine Spec)

- **作者**：Antigravity (Technical Co-Founder) & User
- **狀態**：Approved (已定案)
- **建立日期**：2026-10-07
- **目標標的**：台股核心現貨 (大型電子、高 Beta 景氣循環、ETF 0050)
- **核心目標**：以純做多 (Long Only) 為基準，突破 SMC 低勝率瓶頸，達成 **55% ~ 60%+ 勝率**，且維持單檔年交易量 **15 ~ 30 筆**（投組年總交易量 150 ~ 300 筆）。

---

## 1. 緣起與痛點分析 (Background & Problem Statement)

根據在 `docs/smc_strategy_report.md` 中的初步研究發現：
1. **傳統 SMC 在台股交易次數過低**：日線 (1D) HTF 搭配 5分K 進場，單檔股票一年僅觸發 4 ~ 6 次交易，樣本數過低導致統計顯著性不足。
2. **純 SMC 策略勝率偏低**：勝率約在 25% ~ 33% 間，主要仰賴 3.0 的高盈虧比維持期望值，對實盤心理壓力極大。
3. **回測計算瓶頸**：現行 `run_backtest` 採用逐根 K 線非向量化迴圈，跑 288 次回測需耗時逾 40 分鐘，嚴重阻礙大量參數網格優化與即時監控。

---

## 2. 決策日誌 (Decision Log)

| 決策項目 | 決策結果 | 曾考量之替代方案 | 採納理由 |
| :--- | :--- | :--- | :--- |
| **交易方向** | **純做多 (Long Only) 為核心基準** | 多空雙向、融券放空 | 台股散戶與主力多頭主導，融券有除權息強制回補與券源限制，純做多達標最具實戰意義。 |
| **勝率與頻率標準** | **勝率 $\ge 55\%\sim 60\%$，單檔年交易 $\ge 15\sim 30$ 筆** | 狙擊型 (5~10 筆)、超高頻當沖 | 避免過度擬合的假勝率，確保大數法則與可複製性。 |
| **持倉模式評估** | **當沖 (Day Trade) 與波段 (Swing) 雙軌獨立統計** | 僅測當沖或僅測波段 | 清楚比較台股 4.5 小時交易時間與隔夜跳空風險對勝率與期望值的真實衝擊。 |
| **回測引擎架構** | **向量化特徵快取回測引擎 (Vectorized Pre-Cached Engine)** | 沿用舊架構多進程、信號快照法 | 將運算瓶頸由數十分鐘壓縮至數十秒內，支援萬級參數網格極速掃描。 |

---

## 3. 三位一體高勝率交易策略邏輯 (Strategy Architecture)

策略融合 **SMC (Smart Money Concepts)**、**Dealing Range (區間折溢價)** 與 **Galen Woods PA (價格行為確認)**：

```mermaid
graph TD
    A[第 1 層：HTF 結構環境 (60K/30K)] -->|回踩 60K Order Block 或<br>處於 60K Dealing Range 折價區 (Discount < 50%)| B[第 2 層：流動性清掃 (Liquidity Sweep)]
    B -->|LTF 5K/1K 跌破前低後迅速拉回<br>或刺穿 DR 區間下緣 (Sweep)| C[第 3 層：Galen Woods PA 確認開火]
    C -->|出現 TBF 假跌破反轉棒 或<br>長下影線 Pinbar 拒絕棒| D[開倉多單 Entry]
```

### 3.1 三層過濾漏斗 (Signal Funnel)
1. **結構層 (Context Filter - 60K / 30K)**：
   - 價格必須處於 60K Dealing Range 的 **折價區（Discount Zone，即區間中點 50% 以下）**，或正在測試 60K 多頭 Order Block (OB)。
   - 杜絕在溢價區追高。
2. **流動性層 (Liquidity Filter - 5K)**：
   - 出現 **Sell-Side Liquidity (SSL) 掃蕩**（刺穿局部低點或 DR 下界後收回），確認散戶停損單已被清洗。
3. **確認層 (PA Trigger - 開火鍵)**：
   - 必須出現 **Galen Woods PA 反轉型態**：
     - **TBF (Trend Bar Failure)**：空頭趨勢棒嘗試下殺，隨後立即被強多頭棒吞噬反轉（經典空頭陷阱）。
     - **Pinbar**：下影線長度佔整根 K 線幅度 $\ge 60\%$ 的看多錘狀線。

### 3.2 風控與出場機制 (Risk & Exit Rules)
- **停損 (Stop Loss, SL)**：
  - 設於 PA 訊號棒低點下方 2~3 個 Tick（加滑點緩衝區 `sl_buffer`）。
- **停利 (Take Profit, TP)**：
  - **模式 A (固定盈虧比)**：測試 $1.0R$、$1.2R$、$1.5R$、$2.0R$（短 TP 衝刺 60%+ 超高勝率）。
  - **模式 B (區間中點動態目標)**：以 60K Dealing Range 中線 50% 或對向區間高點平倉。
- **保本機制 (Breakeven, BE)**：
  - 浮盈達 $+0.8R$ 或 $+1.0R$ 時，自動將停損移至進場價位，鎖定零風險。
- **持倉模式**：
  - **當沖 (Day Trade)**：13:20 強制平倉，不留倉。
  - **波段 (Swing)**：最多持倉 3~5 個交易日，遇 TP/SL 或超時再平倉。

---

## 4. 極速向量化回測引擎架構 (Engine Specification)

### 4.1 核心模組
1. **`DataFeaturizer`**：
   - 預先批次讀取標的之 1K / 5K / 60K K 線。
   - 事先在記憶體中計算好所有指標與結構（NumPy 陣列結構化快取）：
     - 60K Dealing Range（High, Low, Mid, Zone）
     - 60K Order Blocks
     - 5K Galen Woods PA 型態（TBF, Pinbar, Reversal）
2. **`FastVectorizedSimulator`**：
   - 接收參數字典（`archetype`, `entry_mode`, `target_rr`, `holding_mode`, `use_breakeven` 等）。
   - 純陣列遮罩模擬，支援千組參數掃描在 30 秒至 1 分鐘內完成。
3. **`StrategyEvaluator`**：
   - 自動生成勝率、交易次數、夏普值、期望值、最大回撤等排名與視覺化摘要。

---

## 5. 邊界與異常狀況處理 (Taiwan Edge Cases)

1. **開盤跳空處理 (Gap Opening)**：
   - 若隔日開盤跳空跌破停損價（SL），必須以真實**開盤價（Open）**撮合成交，不得以理想停損價計算。
2. **漲跌停限制 (10% Price Limit)**：
   - 漲停鎖死棒禁止開倉買進（避免無法成交之無效信號）。
3. **台股交易手續費與稅負**：
   - 買進：0.1425% * 手續費折讓 (預設 6 折)
   - 賣出：0.1425% * 手續費折讓 + 證券交易稅 0.3%（現股當沖則為 0.15%）

---

## 6. 驗證與驗收標準 (Acceptance Criteria)

1. **樣本外檢驗 (Walk-Forward / Out-of-Sample)**：
   - 訓練期 (2025/07 ~ 2026/03) 達到最優參數後，在盲測期 (2026/04 ~ 2026/09) 仍需維持 $\ge 55\%$ 勝率與正期望值。
2. **多族群標的適應性**：
   - 策略配置需在科技權值（2317）、航運（2618）、面板（2409）與大盤（0050）皆能獲取穩定正向分佈。

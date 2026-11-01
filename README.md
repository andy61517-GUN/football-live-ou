# 足球走地大小分分析系統（手機版）

## 功能
- 透過 API-Football 取得進行中的賽事及可用比賽統計
- 全場大小分分析
- 上半場大小分分析（上半場進行中才顯示）
- 使用射門、射正、xG（若 API 有提供）與比賽時間估算剩餘進球期望
- 手動輸入即時全場／上半場盤口
- 手機瀏覽器可用 Streamlit Cloud 部署

## 重要限制
此版本使用透明的簡化啟發式模型，並非經歷史回測校準的預測模型。API-Football 不同方案對即時賽事與統計的覆蓋不同。API 不保證每場都有 xG、危險進攻或完整統計。盤口需手動輸入；本版本沒有自動讀取球版賠率。

## 本機啟動
```bash
pip install -r requirements.txt
streamlit run app.py
```

## API Key
至 https://www.api-football.com/ 註冊並在 Dashboard 取得 API Key。啟動後在左側欄位輸入，不要將金鑰寫入公開程式碼或提交到 GitHub。

## Streamlit Community Cloud 部署
1. 將 `app.py`、`requirements.txt`、`README.md` 上傳到 GitHub repository 根目錄。
2. 在 https://share.streamlit.io/ 建立 App。
3. 選擇 repository、branch `main`、主檔 `app.py`。
4. 部署後在 App 左側輸入 API Key。
5. 可在 Streamlit App settings → Secrets 設定 `API_FOOTBALL_KEY`；若要使用 Secrets，需再把程式改成讀取 `st.secrets`。

## 注意
請先確認 API 方案的額度及統計端點權限。模型只作資料整理與機率估算，不保證結果或獲利。

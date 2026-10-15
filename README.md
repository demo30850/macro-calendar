# 美國總體經濟數據行事曆

訂閱網址：`https://<帳號>.github.io/macro-calendar/macro.ics`

- `schedule.json`：公布時程（BLS、BEA、Fed 官方時程表）。官方公布新年度時程後要補上。
- `consensus.json`：市場預期，key 是 `種類-日期`（例如 `CPI-2026-11-10`），由定時任務在公布前幾天填入。
- `notes.json`：GDP、PCE、FOMC 的上期結果（沒有免金鑰的官方 API，由定時任務在公布後填入）。
- `build.py`：從 BLS 官方 API 抓 CPI、PPI、非農的實際數字，產生 `public/macro.ics`。
- GitHub Actions 每個平日美東 8:30 公布後、以及每晚自動重建並發布到 GitHub Pages。

"""Builds public/macro.ics: US macro releases with previous data, consensus and what a beat/miss means.

Previous/actual figures come from the BLS public API (no key). Consensus comes from
consensus.json, which a scheduled task fills a few days before each release.
"""
import datetime as dt
import hashlib
import json
import pathlib
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).parent
NY = ZoneInfo("America/New_York")

SERIES = {
    "cpi_sa": "CUSR0000SA0", "core_sa": "CUSR0000SA0L1E", "cpi_nsa": "CUUR0000SA0", "core_nsa": "CUUR0000SA0L1E",
    "ppi_sa": "WPSFD4", "ppi_nsa": "WPUFD4", "ppicore_sa": "WPSFD49116", "ppicore_nsa": "WPUFD49116",
    "payrolls": "CES0000000001", "unemployment": "LNS14000000", "wages": "CES0500000003",
}


def fetch_bls():
    year = dt.date.today().year
    body = json.dumps({"seriesid": list(SERIES.values()), "startyear": str(year - 2), "endyear": str(year)}).encode()
    # The BLS API sometimes stalls (a timeout failed the 2026-10-20 run); retry before giving up.
    for attempt in range(4):
        try:
            req = urllib.request.Request("https://api.bls.gov/publicAPI/v1/timeseries/data/", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            break
        except (OSError, ValueError) as error:
            if attempt == 3:
                raise
            print(f"BLS API attempt {attempt + 1} failed ({error}); retrying")
            time.sleep(15 * (attempt + 1))
    if data.get("status") != "REQUEST_SUCCEEDED":
        sys.exit(f"BLS API failed: {data.get('message')}")
    by_id = {s["seriesID"]: s["data"] for s in data["Results"]["series"]}
    out = {}
    for key, sid in SERIES.items():
        out[key] = {(int(p["year"]), int(p["period"][1:])): float(p["value"])
                    for p in by_id.get(sid, []) if p["period"].startswith("M") and p["period"] != "M13" and p["value"] != "-"}
    return out


def prev_month(ym, n=1):
    y, m = ym
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return (y, m)


def pct(series, ym, back):
    a, b = series.get(ym), series.get(prev_month(ym, back))
    return None if a is None or b is None else (a / b - 1) * 100


def fmt(v, sign=True):
    return "—" if v is None else (f"{v:+.1f}%" if sign else f"{v:.1f}%")


def figures(kind, d, ym):
    """Text for one reference month, or None if BLS has not published it yet."""
    y, m = ym
    label = f"{y} 年 {m} 月"
    if kind == "CPI" and ym in d["cpi_sa"]:
        return (f"{label}：CPI 月增 {fmt(pct(d['cpi_sa'], ym, 1))}、年增 {fmt(pct(d['cpi_nsa'], ym, 12))}；"
                f"核心 CPI 月增 {fmt(pct(d['core_sa'], ym, 1))}、年增 {fmt(pct(d['core_nsa'], ym, 12))}")
    if kind == "PPI" and ym in d["ppi_sa"]:
        return (f"{label}：PPI 月增 {fmt(pct(d['ppi_sa'], ym, 1))}、年增 {fmt(pct(d['ppi_nsa'], ym, 12))}；"
                f"核心 PPI（扣除食品、能源與貿易服務）月增 {fmt(pct(d['ppicore_sa'], ym, 1))}、年增 {fmt(pct(d['ppicore_nsa'], ym, 12))}")
    if kind == "NFP" and ym in d["payrolls"] and prev_month(ym) in d["payrolls"]:
        change = (d["payrolls"][ym] - d["payrolls"][prev_month(ym)]) * 1000
        rate = d["unemployment"].get(ym)
        return (f"{label}：非農新增 {change / 10000:+.1f} 萬人；失業率 {fmt(rate, sign=False)}；"
                f"平均時薪月增 {fmt(pct(d['wages'], ym, 1))}、年增 {fmt(pct(d['wages'], ym, 12))}")
    return None


DISCLAIMER = ("※ 以上是市場常見的反應方向，實際走勢還會受其他消息影響，不是投資建議。\n"
              "※ 數字依官方公布的指數計算，偶爾會和新聞報導的數字差 0.1。")

INFO = {
    "CPI": dict(title="🇺🇸 美國 CPI 消費者物價指數", src="https://www.bls.gov/cpi/",
                what="衡量一般民眾買東西的價格變化，是市場最重視的通膨數據，核心 CPI 更受關注。",
                high="高於預期：通膨壓力大 → Fed 升息機率上升 → 美債殖利率、美元走強；股市（特別是科技成長股）和黃金通常下跌。",
                low="低於預期：通膨降溫 → 升息機率下降、降息預期升溫 → 殖利率、美元走弱；股市和黃金通常上漲。"),
    "PPI": dict(title="🇺🇸 美國 PPI 生產者物價指數", src="https://www.bls.gov/ppi/",
                what="衡量企業端（上游）的價格，常被看成 CPI 的領先指標：成本漲了，之後可能轉嫁給消費者。",
                high="高於預期：上游成本壓力大，市場擔心之後 CPI 也會走高 → 殖利率、美元偏強，股市偏弱。",
                low="低於預期：成本壓力減輕 → 對通膨前景較樂觀，殖利率、美元偏弱，股市偏強。"),
    "NFP": dict(title="🇺🇸 美國非農就業報告", src="https://www.bls.gov/ces/",
                what="包含非農就業人數、失業率、平均時薪，是看美國經濟與勞動市場最重要的數據。",
                high="就業高於預期（或失業率低於預期）：經濟強、薪資可能推高通膨 → 升息機率上升 → 美元、殖利率走強；股市反應不一。",
                low="就業低於預期（或失業率高於預期）：經濟轉弱 → 降息預期升溫 → 美元、殖利率走弱；太差會引發衰退擔憂，股市也可能下跌，黃金通常上漲。"),
    "FOMC": dict(title="🏦 Fed 利率決議（FOMC）", src="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                 what="美國聯準會決定利率。美東下午 2:00 公布聲明，2:30 主席記者會。",
                 high="比預期鷹派（升更多、或暗示還要再升）：美元、殖利率走強，股市、黃金承壓。",
                 low="比預期鴿派（沒升、或暗示升息結束）：美元、殖利率走弱，股市、黃金偏強。"),
    "GDP": dict(title="🇺🇸 美國 GDP 經濟成長率", src="https://www.bea.gov/data/gdp/gross-domestic-product",
                what="美國整體經濟成長速度（年化季增率）。初值最受關注，之後還有修正值與終值。",
                high="高於預期：經濟強 → 殖利率、美元偏強；若同時通膨高，會加深升息預期。",
                low="低於預期：經濟轉弱 → 殖利率、美元偏弱；太弱會引發衰退擔憂。"),
    "PCE": dict(title="🇺🇸 美國 PCE 個人消費支出物價", src="https://www.bea.gov/data/personal-consumption-expenditures-price-index",
                what="Fed 最重視的通膨指標（目標 2%），特別是核心 PCE。和個人所得、消費支出一起公布。",
                high="高於預期：通膨壓力大 → 升息機率上升 → 美元、殖利率走強，股市、黃金偏弱。",
                low="低於預期：通膨降溫 → 美元、殖利率走弱，股市、黃金偏強。"),
}


def esc(t):
    return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    b, out = line.encode(), []
    while len(b) > 73:
        cut = 73
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode())
        b = b[cut:]
    out.append(b.decode())
    return "\r\n ".join(out)


def event_id(e):
    return f"{e['kind']}-{e['date']}"


def description(e, data, consensus, notes):
    info = INFO[e["kind"]]
    parts = [info["what"]]
    ym = tuple(e["ref"]) if "ref" in e else None
    actual = figures(e["kind"], data, ym) if ym else None
    previous = figures(e["kind"], data, prev_month(ym)) if ym else None
    if actual:
        parts.append("✅ 公布結果\n" + actual)
    if previous:
        parts.append("上期\n" + previous)
    elif notes.get(event_id(e)):
        parts.append("上期\n" + notes[event_id(e)])
    c = consensus.get(event_id(e))
    if c:
        parts.append(f"市場預期（{c.get('updated', '')} 更新）\n{c['text']}" + (f"\n來源：{c['source']}" if c.get("source") else ""))
    elif not actual:
        parts.append("市場預期：公布前幾天會自動補上。")
    parts.append("📈 " + info["high"])
    parts.append("📉 " + info["low"])
    parts.append("官方資料：" + info["src"])
    parts.append(DISCLAIMER)
    return "\n\n".join(parts)


def build(data):
    schedule = json.loads((ROOT / "schedule.json").read_text())
    consensus = json.loads((ROOT / "consensus.json").read_text())
    notes = json.loads((ROOT / "notes.json").read_text())
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Xuji//Macro Calendar//ZH-TW", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:美國總體經濟數據", "X-WR-TIMEZONE:Asia/Taipei", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
             "X-PUBLISHED-TTL:PT6H",
             "BEGIN:VTIMEZONE", "TZID:America/New_York",
             "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0400", "TZNAME:EDT", "DTSTART:19700308T020000",
             "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
             "BEGIN:STANDARD", "TZOFFSETFROM:-0400", "TZOFFSETTO:-0500", "TZNAME:EST", "DTSTART:19701101T020000",
             "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD", "END:VTIMEZONE"]
    for e in sorted(schedule, key=lambda e: (e["date"], e["time"])):
        info = INFO[e["kind"]]
        start = dt.datetime.strptime(f"{e['date']} {e['time']}", "%Y-%m-%d %H:%M")
        end = start + dt.timedelta(minutes=60 if e["kind"] == "FOMC" else 30)
        summary = info["title"] + (f"（{e['label']}）" if e.get("label") else "")
        uid = hashlib.sha1(event_id(e).encode()).hexdigest()[:16] + "@xuji-macro"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID=America/New_York:{start:%Y%m%dT%H%M%S}", f"DTEND;TZID=America/New_York:{end:%Y%m%dT%H%M%S}",
                  fold("SUMMARY:" + esc(summary)), fold("DESCRIPTION:" + esc(description(e, data, consensus, notes))),
                  fold("URL:" + info["src"]),
                  "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT30M", fold("DESCRIPTION:" + esc(summary)), "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    out = ROOT / "public"
    out.mkdir(exist_ok=True)
    (out / "macro.ics").write_bytes(("\r\n".join(lines) + "\r\n").encode())
    return len(schedule)


if __name__ == "__main__":
    print(f"built {build(fetch_bls())} events")

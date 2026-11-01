import math
import requests
import streamlit as st

st.set_page_config(page_title="足球＋NBA 走地大小分分析", page_icon="🏀", layout="wide")

st.title("⚽🏀 足球＋NBA 走地大小分分析")
sport_tab = st.radio("選擇分析項目", ["⚽ 足球", "🏀 NBA"], horizontal=True)

def poisson_tail(lam, needed):
    if needed <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    return 1 - sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(needed))

def ou_probabilities(current_points, line, lam):
    adjusted = float(line) - current_points
    if abs(adjusted - round(adjusted)) < 1e-9:
        n = int(round(adjusted))
        over = poisson_tail(lam, n + 1)
        under = poisson_tail(lam, n)
        push = math.exp(-lam) * lam**n / math.factorial(n) if n >= 0 else 0.0
        return over, under, push
    return poisson_tail(lam, math.floor(adjusted) + 1), poisson_tail(lam, math.ceil(adjusted)), 0.0

def pct(x):
    return f"{x:.1%}"

# ---------------- FOOTBALL ----------------
def football_page():
    st.subheader("⚽ 足球走地分析")
    st.caption("資料來源：5DollarFootballAPI")
    api_base = st.secrets.get("FOOTBALL_API_BASE", "https://api.5dollarfootballapi.com/v1").rstrip("/")
    api_key = st.secrets.get("FOOTBALL_API_KEY", "")
    if not api_key:
        st.error("找不到 FOOTBALL_API_KEY。請到 Streamlit Cloud → Settings → Secrets 確認設定。")
        return

    @st.cache_data(ttl=60, show_spinner=False)
    def get_football_live(base, key):
        r = requests.get(
            f"{base}/fixtures",
            headers={"Authorization": f"Bearer {key}"},
            params={"status": "live", "per_page": 50},
            timeout=25,
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("success") != 1:
            raise RuntimeError(f"足球 API 回傳錯誤：{payload}")
        return payload.get("data") or []

    @st.cache_data(ttl=60, show_spinner=False)
    def get_football_stats(base, key, fixture_id):
        r = requests.get(
            f"{base}/fixtures/{fixture_id}/statistics",
            headers={"Authorization": f"Bearer {key}"},
            timeout=25,
        )
        r.raise_for_status()
        payload = r.json()
        return (payload.get("data") or {}).get("statistics") or {}

    c1, c2 = st.columns([3, 1])
    c1.write("即時比賽列表（每 60 秒快取）")
    if c2.button("🔄 更新足球賽事", use_container_width=True):
        get_football_live.clear()
        get_football_stats.clear()
        st.rerun()
    try:
        fixtures = get_football_live(api_base, api_key)
    except Exception as e:
        st.error(f"足球資料讀取失敗：{e}")
        return
    if not fixtures:
        st.info("目前 API 沒有回傳進行中的足球賽事。可稍後重新整理；NBA 功能不受影響。")
        st.markdown("[5DollarFootballAPI](https://5dollarfootballapi.com/)")
        return

    def fixture_label(f):
        teams = f.get("teams") or {}
        h = (teams.get("home") or {}).get("name", "主隊")
        a = (teams.get("away") or {}).get("name", "客隊")
        g = f.get("goals") or {}
        score = f'{g.get("home") if g.get("home") is not None else "-"} : {g.get("away") if g.get("away") is not None else "-"}'
        league = (f.get("league") or {}).get("name", "未知聯賽")
        return f'{league}｜{h} {score} {a}｜{f.get("status_code") or "進行中"}'

    labels = [fixture_label(f) for f in fixtures]
    selected = st.selectbox("選擇足球比賽", labels)
    fixture = fixtures[labels.index(selected)]
    teams = fixture.get("teams") or {}
    home = (teams.get("home") or {}).get("name", "主隊")
    away = (teams.get("away") or {}).get("name", "客隊")
    goals = fixture.get("goals") or {}
    hg, ag = goals.get("home") or 0, goals.get("away") or 0
    total = hg + ag
    status = str(fixture.get("status_code") or "")
    halftime = status.lower() == "half"
    minute = int(status) if status.isdigit() else (45 if halftime else 0)
    try:
        stats = get_football_stats(api_base, api_key, fixture.get("id"))
    except Exception:
        stats = {}
    st.markdown(f"### {home} {hg} : {ag} {away}")
    st.caption(f'{(fixture.get("league") or {}).get("name", "未知聯賽")}｜{"中場休息" if halftime else str(minute) + " 分鐘"}')
    sot, soff = stats.get("shots_on_target"), stats.get("shots_off_target")
    shots = None
    if isinstance(sot, dict) and isinstance(soff, dict) and all(sot.get(k) is not None and soff.get(k) is not None for k in ("home", "away")):
        shots = {"home": sot["home"] + soff["home"], "away": sot["away"] + soff["away"]}
    def pair(obj, suffix=""):
        if not isinstance(obj, dict) or obj.get("home") is None or obj.get("away") is None:
            return "尚無資料"
        return f'{obj["home"]}{suffix} / {obj["away"]}{suffix}'
    cards = fixture.get("cards") or {}
    hc, ac = cards.get("home") or {}, cards.get("away") or {}
    red = (hc.get("red") or 0) + (ac.get("red") or 0)
    values = [
        ("射門", pair(shots)), ("射正", pair(sot)), ("射偏", pair(soff)),
        ("危險進攻", pair(stats.get("dangerous_attacks"))), ("總進攻", pair(stats.get("attacks"))),
        ("控球率", pair(stats.get("possession"), "%")), ("角球", pair(fixture.get("corners"))),
        ("紅牌", str(red) if hc.get("red") is not None and ac.get("red") is not None else "尚無資料"),
    ]
    cols = st.columns(4)
    for i, (name, value) in enumerate(values):
        cols[i % 4].metric(name, value)
    if not stats:
        st.warning("此場暫無統計資料，缺少項目不會以 0 代替。")

    full_line = st.number_input("足球全場大小分盤口", 0.5, 10.0, 2.5, 0.25, key="football_full")
    half_line = st.number_input("足球上半場大小分盤口", 0.5, 5.0, 1.0, 0.25, key="football_half")
    def football_lambda(m, data, first=False):
        block = (data or {}).get("first_half", {}) if first else (data or {})
        remaining = max(0, (45 if first else 90) - m)
        lam = remaining * (1 / 45 if first else 1.05 / 90)
        s = block.get("shots_on_target")
        d = block.get("dangerous_attacks")
        if isinstance(s, dict):
            n = (s.get("home") or 0) + (s.get("away") or 0)
            lam *= min(1.65, max(0.65, 0.85 + n * 0.055))
        if isinstance(d, dict):
            n = (d.get("home") or 0) + (d.get("away") or 0)
            lam *= min(1.25, max(0.80, 0.90 + n / 300))
        return min(3.5, max(0, lam))
    lam = football_lambda(minute, stats)
    o, u, p = ou_probabilities(total, full_line, lam)
    a, b, c = st.columns(3)
    a.metric("全場預估剩餘進球", f"{lam:.2f}")
    b.metric("大分估算", pct(o))
    c.metric("小分估算", pct(u))
    if p > .001:
        st.caption(f"整數盤走水機率約 {pct(p)}。")
    st.markdown("#### 上半場大小分")
    if halftime or minute > 45:
        st.info("上半場已結束，不再估算上半場剩餘進球。")
    else:
        hlam = football_lambda(minute, stats, True)
        ho, hu, hp = ou_probabilities(total, half_line, hlam)
        a, b, c = st.columns(3)
        a.metric("上半場預估剩餘進球", f"{hlam:.2f}")
        b.metric("上半場大分估算", pct(ho))
        c.metric("上半場小分估算", pct(hu))
    st.caption("足球估算為簡化 Poisson 節奏模型，非保證命中率。資料來源：[5DollarFootballAPI](https://5dollarfootballapi.com/)")

# ---------------- NBA ----------------
def nba_page():
    st.subheader("🏀 NBA 走地分析")
    st.caption("資料來源：ESPN 公開賽事資料介面（無需 API Key；非官方開發者 API）")
    BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

    @st.cache_data(ttl=30, show_spinner=False)
    def nba_scoreboard():
        r = requests.get(f"{BASE}/scoreboard", params={"limit": 300}, timeout=20)
        r.raise_for_status()
        return r.json()

    @st.cache_data(ttl=30, show_spinner=False)
    def nba_summary(event_id):
        r = requests.get(f"{BASE}/summary", params={"event": event_id}, timeout=20)
        r.raise_for_status()
        return r.json()

    col1, col2 = st.columns([3, 1])
    col1.write("NBA 今日賽事與即時比分")
    if col2.button("🔄 更新 NBA 賽事", use_container_width=True):
        nba_scoreboard.clear()
        nba_summary.clear()
        st.rerun()
    try:
        board = nba_scoreboard()
    except Exception as e:
        st.error(f"NBA 賽程讀取失敗：{e}")
        return
    events = board.get("events") or []
    if not events:
        st.info("目前 ESPN 沒有回傳今日 NBA 賽事。")
        return

    def event_status(event):
        comp = (event.get("competitions") or [{}])[0]
        status = comp.get("status") or event.get("status") or {}
        typ = status.get("type") or {}
        return typ.get("detail") or typ.get("shortDetail") or typ.get("description") or "賽事狀態未知"

    def event_label(event):
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        away = next((x for x in competitors if x.get("homeAway") == "away"), {})
        home = next((x for x in competitors if x.get("homeAway") == "home"), {})
        an = (away.get("team") or {}).get("displayName", "客隊")
        hn = (home.get("team") or {}).get("displayName", "主隊")
        return f'{an} {away.get("score", "-")} @ {hn} {home.get("score", "-")}｜{event_status(event)}'

    labels = [event_label(e) for e in events]
    selected = st.selectbox("選擇 NBA 比賽", labels)
    event = events[labels.index(selected)]
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    away = next((x for x in competitors if x.get("homeAway") == "away"), {})
    home = next((x for x in competitors if x.get("homeAway") == "home"), {})
    away_name = (away.get("team") or {}).get("displayName", "客隊")
    home_name = (home.get("team") or {}).get("displayName", "主隊")
    away_score = int(away.get("score") or 0)
    home_score = int(home.get("score") or 0)
    total = away_score + home_score
    status = comp.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    status_name = status_type.get("name", "")
    status_detail = status_type.get("detail") or status_type.get("shortDetail") or "狀態未知"
    period = status.get("period") or 0
    clock = status.get("displayClock") or ""
    live = status_name == "STATUS_IN_PROGRESS"
    completed = status_name == "STATUS_FINAL"

    st.markdown(f"### {away_name} {away_score} : {home_score} {home_name}")
    st.caption(f"比賽狀態：{status_detail}　｜　節數：{period if period else '—'}　｜　剩餘時間：{clock or '—'}")
    # 顯示每節得分
    lines = []
    for side_name, team in [("客隊", away), ("主隊", home)]:
        vals = team.get("linescores") or []
        lines.append({"球隊": side_name, **{f"第{i+1}節": (v.get("displayValue") or v.get("value") or "—") for i, v in enumerate(vals)}})
    if any(len(x) > 1 for x in lines):
        st.markdown("#### 各節比分")
        st.dataframe(lines, hide_index=True, use_container_width=True)

    try:
        summary = nba_summary(event.get("id"))
    except Exception as e:
        summary = {}
        st.warning(f"詳細技術統計暫時讀取失敗：{e}")
    box = summary.get("boxscore") or {}
    team_stats = box.get("teams") or []
    if team_stats:
        st.markdown("#### 球隊技術統計")
        stat_rows = []
        for item in team_stats:
            team_info = item.get("team") or {}
            row = {"球隊": team_info.get("displayName", "球隊")}
            for stat in item.get("statistics") or []:
                name = stat.get("label") or stat.get("name")
                value = stat.get("displayValue") or stat.get("value")
                if name:
                    row[name] = value
            stat_rows.append(row)
        st.dataframe(stat_rows, hide_index=True, use_container_width=True)
    else:
        st.info("目前尚未取得球隊技術統計；未提供的數據不會顯示為 0。")

    st.markdown("### 🎯 NBA 大小分估算")
    line = st.number_input("NBA 全場大小分盤口", 100.5, 300.0, 220.5, 0.5, key="nba_full_line")
    if live and period:
        # NBA 正規賽 48 分鐘；延長賽不納入剩餘時間的簡化估算
        elapsed = min(48.0, max(0.0, (period - 1) * 12 + (12 - 0)))
        try:
            mins_left_in_period = float(clock.split(":")[0]) + float(clock.split(":")[1]) / 60 if ":" in clock else 0.0
            elapsed = min(48.0, max(0.0, (period - 1) * 12 + (12 - mins_left_in_period)))
        except Exception:
            pass
        remaining = max(0.0, 48.0 - elapsed)
        pace = total / max(elapsed, 1.0)
        projected_remaining = pace * remaining
        # 回歸至 NBA 常見節奏附近，降低極短時間樣本的劇烈波動
        projected_remaining = 0.65 * projected_remaining + 0.35 * (remaining * 4.6)
        sigma = max(5.0, math.sqrt(max(projected_remaining, 1.0)) * 2.2)
        mean_final = total + projected_remaining
        z = (line - 0.5 - mean_final) / sigma
        over_p = 0.5 * (1 + math.erf(-z / math.sqrt(2)))
        under_p = 1 - over_p
        a, b, c = st.columns(3)
        a.metric("目前總分", total)
        b.metric("預估全場總分", f"{mean_final:.1f}")
        c.metric("剩餘預估得分", f"{projected_remaining:.1f}")
        d, e = st.columns(2)
        d.metric("大分估算", pct(over_p))
        e.metric("小分估算", pct(under_p))
        st.caption("此為簡化節奏投影，不是經回測的預測模型；比分差距、犯規戰術、球員輪換及延長賽均可能影響結果。")
    elif completed:
        st.info("比賽已結束，沒有剩餘時間可供走地估算。")
    else:
        st.info("比賽尚未開打。可先查看賽程；開賽後會顯示走地總分估算。")
    st.caption("NBA 資料來源：[ESPN](https://www.espn.com/nba/)｜比分快取 30 秒")

if sport_tab == "⚽ 足球":
    football_page()
else:
    nba_page()

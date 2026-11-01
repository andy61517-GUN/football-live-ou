
import math
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(page_title="足球走地大小分分析", page_icon="⚽", layout="wide")

API_BASE = "https://v3.football.api-sports.io"

def api_get(path, api_key, params=None):
    r = requests.get(API_BASE + path, headers={"x-apisports-key": api_key}, params=params or {}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data.get("response", [])

def val_num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def norm(s):
    return str(s or "").strip().lower()

def stat_map(rows):
    out = {}
    for item in rows or []:
        k = norm(item.get("type"))
        v = item.get("value")
        if isinstance(v, str) and "%" in v:
            v = v.replace("%", "")
        out[k] = val_num(v, 0)
    return out

def poisson_prob_at_least(lam, n):
    if n <= 0:
        return 1.0
    cdf = sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(n))
    return max(0.0, min(1.0, 1.0-cdf))

def poisson_prob_at_most(lam, n):
    if n < 0:
        return 0.0
    return max(0.0, min(1.0, sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(n+1))))

def get_stat(m, *keys):
    for k in keys:
        if k in m:
            return m[k]
    return 0.0

def estimate_remaining(home, away, minute, score_total, period, red_home=0, red_away=0):
    # Transparent heuristic, not a trained model. API-Football xG is used when available.
    elapsed = min(max(minute, 1), 90)
    remaining = max(0, 95-elapsed)
    xg_h = get_stat(home, "expected_goals", "xg")
    xg_a = get_stat(away, "expected_goals", "xg")
    shots_h = get_stat(home, "total_shots")
    shots_a = get_stat(away, "total_shots")
    sot_h = get_stat(home, "shots_on_goal", "shots on goal")
    sot_a = get_stat(away, "shots_on_goal", "shots on goal")
    dangerous_h = get_stat(home, "dangerous_attacks")
    dangerous_a = get_stat(away, "dangerous_attacks")

    # Base live scoring intensity; adjusted by observed threat metrics where available.
    lam = 1.05 * remaining / 30.0
    evidence = []
    if xg_h + xg_a > 0:
        # Scale live xG to remaining-time intensity without treating accumulated xG as future goals.
        xg_rate = (xg_h + xg_a) / max(elapsed, 15) * remaining
        lam = 0.55 * lam + 0.45 * min(2.2, max(0.05, xg_rate * 0.72))
        evidence.append("有 xG 數據")
    if shots_h + shots_a > 0:
        shot_factor = 1 + min(0.30, max(-0.15, ((sot_h+sot_a)/max(shots_h+shots_a,1)-0.30)*0.8))
        lam *= shot_factor
        evidence.append("有射門／射正數據")
    # A trailing side may attack more late; only a modest adjustment.
    if minute >= 55 and abs(val_num(st.session_state.get("home_goals",0))-val_num(st.session_state.get("away_goals",0))) == 1:
        lam *= 1.08
        evidence.append("一球差距的後段比分修正")
    if red_home + red_away:
        # Red cards increase variance, not reliably the mean. Small adjustment only.
        lam *= 1.04
        evidence.append("有紅牌：模型不確定性提高")
    lam = max(0.02, min(4.0, lam))
    return lam, remaining, evidence, {"xg": xg_h+xg_a, "shots": shots_h+shots_a, "sot": sot_h+sot_a}

def asian_over_under(lam, current_goals, line):
    # Whole/half/quarter totals approximated by adjacent half-point lines.
    # Push probability is reported for integer lines.
    over_need = math.floor(line - current_goals) + 1
    under_max = math.ceil(line - current_goals) - 1
    p_over = poisson_prob_at_least(lam, max(0, over_need))
    p_under = poisson_prob_at_most(lam, under_max)
    push = 0.0
    if abs((line-current_goals) - round(line-current_goals)) < 1e-8:
        n = int(round(line-current_goals))
        if n >= 0:
            push = math.exp(-lam)*lam**n/math.factorial(n)
    return p_over, p_under, push

st.title("⚽ 足球走地大小分分析系統")
st.caption("手機優先介面｜全場＋上半場｜即時賽事與統計需 API-Football 金鑰")
with st.sidebar:
    st.header("資料連線")
    api_key = st.text_input("API-Football API Key", type="password", help="到 dashboard.api-football.com 註冊取得。金鑰只在本次執行的介面中使用，不要貼到公開程式碼。")
    st.caption("API-Football 免費方案可能有每日請求額度及賽事統計覆蓋限制。")
    refresh = st.button("↻ 重新抓取即時賽事", use_container_width=True)
    st.divider()
    st.caption("模型說明：這是透明的基礎估算模型，並非經歷史回測校準的專業預測器。")

if not api_key:
    st.info("先在左側輸入 API-Football API Key，再載入即時賽事。")
    st.markdown("**取得方式：** [API-Football 官方網站](https://www.api-football.com/) → 註冊 → Dashboard → 複製 API Key。")
    st.markdown("上線前請先確認你的方案允許即時賽事與 fixtures statistics。")
    st.stop()

if "fixtures" not in st.session_state or refresh:
    try:
        with st.spinner("正在取得即時比賽…"):
            st.session_state.fixtures = api_get("/fixtures", api_key, {"live":"all"})
    except Exception as e:
        st.error(f"讀取即時賽事失敗：{e}")
        st.stop()

fixtures = st.session_state.fixtures
if not fixtures:
    st.warning("目前 API 沒有回傳進行中的比賽。可稍後重新整理，或確認 API 方案權限。")
    st.stop()

options = {}
for f in fixtures:
    teams=f.get("teams",{})
    goals=f.get("goals",{})
    status=f.get("fixture",{}).get("status",{})
    minute=status.get("elapsed") or 0
    label=f"{teams.get('home',{}).get('name','主隊')} {goals.get('home') or 0}-{goals.get('away') or 0} {teams.get('away',{}).get('name','客隊')}｜{minute}'"
    options[label]=f

selected_label = st.selectbox("選擇進行中的比賽", list(options.keys()))
fixture=options[selected_label]
fid=fixture["fixture"]["id"]
teams=fixture["teams"]
goals=fixture["goals"]
home_name=teams["home"]["name"]; away_name=teams["away"]["name"]
hg=int(goals.get("home") or 0); ag=int(goals.get("away") or 0)
minute=int(fixture["fixture"]["status"].get("elapsed") or 0)
status_short=fixture["fixture"]["status"].get("short","")
st.session_state.home_goals=hg; st.session_state.away_goals=ag

try:
    with st.spinner("讀取比賽統計…"):
        raw_stats=api_get("/fixtures/statistics",api_key,{"fixture":fid})
    home_stats=stat_map(raw_stats[0].get("statistics",[])) if len(raw_stats)>0 else {}
    away_stats=stat_map(raw_stats[1].get("statistics",[])) if len(raw_stats)>1 else {}
except Exception as e:
    home_stats={}; away_stats={}
    st.warning(f"暫時無法取得詳細統計，將使用比分與時間基準估算。原因：{e}")

red_h=get_stat(home_stats,"red_cards"); red_a=get_stat(away_stats,"red_cards")
lam, remaining, evidence, raw=estimate_remaining(home_stats,away_stats,minute,hg+ag,"full",red_h,red_a)

c1,c2,c3=st.columns(3)
c1.metric("比賽時間", f"{minute}'")
c2.metric("目前比分", f"{hg} - {ag}")
c3.metric("目前總進球", hg+ag)
st.subheader("即時比賽數據")
rows=[]
for label,key in [("射門","total_shots"),("射正","shots_on_goal"),("危險進攻","dangerous_attacks"),("控球率","ball_possession"),("角球","corner_kicks"),("紅牌","red_cards"),("預期進球 xG","expected_goals")]:
    hv=get_stat(home_stats,key); av=get_stat(away_stats,key)
    rows.append({"數據":label,home_name:hv,away_name:av})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.subheader("全場大小分分析")
st.metric("模型預測剩餘進球期望", f"{lam:.2f}", help="簡化啟發式模型估算，不是保證結果。")
st.metric("模型預測最終總進球期望", f"{hg+ag+lam:.2f}")
line_full=st.number_input("輸入目前全場大小盤（例如 2.5、3.0、3.25）", min_value=0.5, max_value=8.0, value=2.5, step=0.25)
pov, pun, push=asian_over_under(lam,hg+ag,line_full)
a,b,c=st.columns(3)
a.metric("大球估計機率",f"{pov*100:.1f}%")
b.metric("小球估計機率",f"{pun*100:.1f}%")
c.metric("走盤機率（整數盤）",f"{push*100:.1f}%")

st.subheader("上半場大小分分析")
ht=fixture.get("score",{}).get("halftime",{}) or {}
ht_total=(ht.get("home") or 0)+(ht.get("away") or 0)
if minute <= 45:
    ht_elapsed=max(1,minute)
    ht_remaining=max(0,50-minute)
    ht_lam=1.05*ht_remaining/30
    if raw["xg"]>0:
        ht_lam=0.65*ht_lam+0.35*min(1.6,raw["xg"]/max(minute,15)*ht_remaining*0.72)
    ht_line=st.number_input("輸入上半場大小盤",min_value=0.5,max_value=5.0,value=1.5,step=0.25)
    hp_over,hp_under,hp_push=asian_over_under(ht_lam,hg+ag,ht_line)
    x,y,z=st.columns(3)
    x.metric("上半場預測剩餘進球",f"{ht_lam:.2f}")
    y.metric("上半場大球機率",f"{hp_over*100:.1f}%")
    z.metric("上半場小球機率",f"{hp_under*100:.1f}%")
else:
    st.info(f"比賽已進入下半場。上半場完場比分：{ht.get('home','?')} - {ht.get('away','?')}；上半場盤口不再提供即時下注判斷。")

st.subheader("模型資料品質與判讀")
if evidence:
    st.write("目前可用訊號：" + "、".join(evidence))
else:
    st.warning("目前缺少射門或 xG 等細部數據，預測主要依賴時間基準，可信度偏低。")
if raw["xg"] == 0:
    st.warning("沒有取得 xG。請勿把此結果視為高信心訊號。")
st.caption("重要：API 統計可能延遲、缺漏或不涵蓋所有聯賽。此工具不含自動賠率來源；盤口需依球版即時數字手動輸入。")
st.caption("預測機率未經足量歷史回測與校準，不構成投注建議。請設定預算並避免追損。")

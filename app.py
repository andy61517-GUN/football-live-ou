import math
import requests
import streamlit as st

st.set_page_config(page_title="足球走地大小分分析", page_icon="⚽", layout="wide")

API_BASE = st.secrets.get("FOOTBALL_API_BASE", "https://api.5dollarfootballapi.com/v1").rstrip("/")
API_KEY = st.secrets.get("FOOTBALL_API_KEY", "")

st.title("⚽ 足球走地大小分分析")
st.caption("即時比分與比賽數據｜估算僅供參考，不代表投注結果")

if not API_KEY:
    st.error("找不到 API Key。請到 Streamlit Cloud → Settings → Secrets，確認 FOOTBALL_API_KEY 已設定。")
    st.stop()


@st.cache_data(ttl=60, show_spinner=False)
def get_live_fixtures(api_base, api_key):
    response = requests.get(
        f"{api_base}/fixtures",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"status": "live", "per_page": 50, "include": "stats", "lang": "zh-tw"},
        timeout=25,
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:500]
        raise RuntimeError(f"API 回應 {response.status_code}：{detail}")
    payload = response.json()
    if payload.get("success") != 1:
        raise RuntimeError(f"API 回傳錯誤：{payload}")
    return payload.get("data") or []


def pair_text(obj, suffix=""):
    if not isinstance(obj, dict) or obj.get("home") is None or obj.get("away") is None:
        return "尚無資料"
    return f'{obj["home"]}{suffix} / {obj["away"]}{suffix}'


def poisson_tail(lam, needed):
    if needed <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    return 1 - sum(math.exp(-lam) * lam**k / math.factorial(k) for k in range(needed))


def estimate_lambda(minute, stats, first_half=False):
    block = (stats or {}).get("first_half", {}) if first_half else (stats or {})
    remaining = max(0, (45 if first_half else 90) - minute)
    rate = (1.0 / 45 if first_half else 1.05 / 90)
    lam = remaining * rate
    sot = block.get("shots_on_target")
    dangerous = block.get("dangerous_attacks")
    if isinstance(sot, dict):
        count = (sot.get("home") or 0) + (sot.get("away") or 0)
        lam *= min(1.65, max(0.65, 0.85 + count * 0.055))
    if isinstance(dangerous, dict):
        count = (dangerous.get("home") or 0) + (dangerous.get("away") or 0)
        lam *= min(1.25, max(0.80, 0.90 + count / 300))
    return max(0.0, min(lam, 3.5))


def ou_probabilities(current_goals, line, lam):
    adjusted = float(line) - current_goals
    if abs(adjusted - round(adjusted)) < 1e-9:
        n = int(round(adjusted))
        over = poisson_tail(lam, n + 1)
        under = poisson_tail(lam, n)
        push = math.exp(-lam) * lam**n / math.factorial(n) if n >= 0 else 0.0
        return over, under, push
    return poisson_tail(lam, math.floor(adjusted) + 1), poisson_tail(lam, math.ceil(adjusted)), 0.0


def label_fixture(f):
    teams = f.get("teams") or {}
    home = (teams.get("home") or {}).get("name", "主隊")
    away = (teams.get("away") or {}).get("name", "客隊")
    goals = f.get("goals") or {}
    score = f'{goals.get("home") if goals.get("home") is not None else "-"} : {goals.get("away") if goals.get("away") is not None else "-"}'
    league = (f.get("league") or {}).get("name", "未知聯賽")
    return f'{league}｜{home} {score} {away}｜{f.get("status_code") or "進行中"}'


try:
    fixtures = get_live_fixtures(API_BASE, API_KEY)
except requests.exceptions.RequestException as exc:
    st.error(f"連線失敗：{exc}")
    st.stop()
except Exception as exc:
    st.error(str(exc))
    st.info("請確認 API Key、方案權限與 API 服務狀態。")
    st.stop()

a, b = st.columns([3, 1])
a.write(f"目前取得 **{len(fixtures)}** 場進行中比賽")
if b.button("🔄 重新整理", use_container_width=True):
    get_live_fixtures.clear()
    st.rerun()

if not fixtures:
    st.info("目前沒有 API 回傳的進行中比賽，請稍後重新整理。")
    st.markdown("[資料來源：5DollarFootballAPI](https://5dollarfootballapi.com/)")
    st.stop()

labels = [label_fixture(f) for f in fixtures]
chosen = st.selectbox("選擇比賽", labels)
fixture = fixtures[labels.index(chosen)]

teams = fixture.get("teams") or {}
home = (teams.get("home") or {}).get("name", "主隊")
away = (teams.get("away") or {}).get("name", "客隊")
goals = fixture.get("goals") or {}
hg, ag = goals.get("home") or 0, goals.get("away") or 0
total_goals = hg + ag
status_code = str(fixture.get("status_code") or "")
half_time = status_code.lower() == "half"
minute = int(status_code) if status_code.isdigit() else (45 if half_time else 0)
stats = fixture.get("statistics") or {}
if not stats and isinstance(fixture.get("stats"), dict):
    stats = fixture["stats"].get("statistics") or fixture["stats"]

st.subheader(f"{home}  vs  {away}")
st.caption(f'{(fixture.get("league") or {}).get("name", "未知聯賽")}｜{ "中場休息" if half_time else (str(minute) + " 分鐘" if minute else "進行中")}')
c1, c2, c3 = st.columns(3)
c1.metric(home, hg)
c2.metric("目前總進球", total_goals)
c3.metric(away, ag)

st.markdown("### 📊 比賽數據")
sot, soff = stats.get("shots_on_target"), stats.get("shots_off_target")
shots = None
if isinstance(sot, dict) and isinstance(soff, dict) and all(
    sot.get(k) is not None and soff.get(k) is not None for k in ("home", "away")
):
    shots = {"home": sot["home"] + soff["home"], "away": sot["away"] + soff["away"]}
cards = fixture.get("cards") or {}
hc, ac = cards.get("home") or {}, cards.get("away") or {}
red = (hc.get("red") or 0) + (ac.get("red") or 0)
red_text = str(red) if hc.get("red") is not None and ac.get("red") is not None else "尚無資料"
items = [
    ("總射門", pair_text(shots)), ("射正", pair_text(sot)), ("射偏", pair_text(soff)),
    ("危險進攻", pair_text(stats.get("dangerous_attacks"))),
    ("總進攻", pair_text(stats.get("attacks"))),
    ("控球率", pair_text(stats.get("possession"), "%")),
    ("角球", pair_text(fixture.get("corners"))), ("紅牌", red_text),
]
grid = st.columns(4)
for i, (name, value) in enumerate(items):
    grid[i % 4].metric(name, value)
if not stats:
    st.warning("這場比賽尚未取得統計資料；缺少數據會顯示「尚無資料」，不會假裝是 0。")

st.markdown("### 🎯 大小分估算")
st.caption("輸入目前盤口。估算為簡化 Poisson 節奏模型，不是莊家賠率或保證命中率。")
full_line = st.number_input("全場大小分盤口", 0.5, 10.0, 2.5, 0.25)
half_line = st.number_input("上半場大小分盤口", 0.5, 5.0, 1.0, 0.25)

lam = estimate_lambda(minute, stats)
over, under, push = ou_probabilities(total_goals, full_line, lam)
x, y, z = st.columns(3)
x.metric("全場預估剩餘進球", f"{lam:.2f}")
y.metric("大分估算", f"{over:.1%}")
z.metric("小分估算", f"{under:.1%}")
if push > 0.001:
    st.caption(f"整數盤走水機率約 {push:.1%}（模型估算）。")

st.divider()
st.markdown("#### 上半場大小分")
if half_time or minute > 45:
    st.info("比賽已進入中場或下半場，上半場已結束，不再估算上半場剩餘進球。")
else:
    half_lam = estimate_lambda(minute, stats, first_half=True)
    ho, hu, hp = ou_probabilities(total_goals, half_line, half_lam)
    x, y, z = st.columns(3)
    x.metric("上半場預估剩餘進球", f"{half_lam:.2f}")
    y.metric("上半場大分估算", f"{ho:.1%}")
    z.metric("上半場小分估算", f"{hu:.1%}")
    if hp > 0.001:
        st.caption(f"上半場整數盤走水機率約 {hp:.1%}。")

st.warning("此模型未完整納入球隊實力、紅牌發生時間、戰術變化及即時盤口，請勿單憑估算下注。")
st.markdown("---")
st.markdown("資料來源：[5DollarFootballAPI](https://5dollarfootballapi.com/)｜資料快取 60 秒")

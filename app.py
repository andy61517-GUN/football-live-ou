import math
import requests
import streamlit as st

st.set_page_config(page_title="足球＋NBA 走地大小分分析", page_icon="🏀", layout="wide")

# 個人使用密碼
app_password = st.secrets.get("APP_PASSWORD", "")
if not app_password:
    st.error("尚未設定 APP_PASSWORD，請至 Streamlit Secrets 設定。")
    st.stop()

if not st.session_state.get("authenticated", False):
    st.title("🔒 個人分析網站登入")
    entered = st.text_input("請輸入個人使用密碼", type="password")
    if st.button("登入"):
        if entered == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    st.stop()

st.title("⚽🏀 足球＋NBA 走地大小分分析")
sport_tab = st.radio("選擇分析項目", ["⚽ 足球", "🏀 NBA"], horizontal=True)


def poisson_tail(lam, needed):
    if needed <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    return 1 - sum(
        math.exp(-lam) * lam**k / math.factorial(k)
        for k in range(needed)
    )


def ou_probabilities(current_points, line, lam):
    adjusted = float(line) - current_points
    if abs(adjusted - round(adjusted)) < 1e-9:
        n = int(round(adjusted))
        over = poisson_tail(lam, n + 1)
        under = poisson_tail(lam, n)
        push = (
            math.exp(-lam) * lam**n / math.factorial(n)
            if n >= 0 else 0.0
        )
        return over, under, push

    return (
        poisson_tail(lam, math.floor(adjusted) + 1),
        poisson_tail(lam, math.ceil(adjusted)),
        0.0
    )


def pct(x):
    return f"{x:.1%}"


# ---------------- THE RUNDOWN 賽前盤口 ----------------

TR_BASE = "https://therundown.io/api/v2"

SOCCER_SPORTS_FALLBACK = {
    10: "美職 MLS",
    11: "英超 EPL",
    12: "法甲 Ligue 1",
    13: "德甲 Bundesliga",
    14: "西甲 La Liga",
    15: "義甲 Serie A",
    16: "歐冠 UEFA Champions League",
    17: "歐霸 UEFA Europa League",
    18: "世界盃 FIFA World Cup",
    19: "日職 J1 League",
    33: "歐協聯 UEFA Conference League",
    34: "墨超 Liga MX",
}


@st.cache_data(ttl=3600, show_spinner=False)
def rundown_soccer_sports(api_key):
    """從 API 目錄取得目前可用的足球聯賽。"""
    response = requests.get(
        f"{TR_BASE}/sports",
        headers={"X-TheRundown-Key": api_key},
        timeout=20
    )
    response.raise_for_status()
    payload = response.json()

    items = payload.get("sports") or payload.get("data") or []
    found = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        sid = item.get("sport_id", item.get("id"))
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            continue

        name = (
            item.get("sport_name")
            or item.get("name")
            or item.get("title")
        )

        category = " ".join(
            str(item.get(k, ""))
            for k in ("category", "sport", "group", "sport_type")
        ).lower()

        if (
            "soccer" in category
            or "football" in category
            or sid in SOCCER_SPORTS_FALLBACK
        ):
            found[sid] = str(
                name or SOCCER_SPORTS_FALLBACK.get(
                    sid, f"足球聯賽 {sid}"
                )
            )

    if not found:
        found = dict(SOCCER_SPORTS_FALLBACK)

    return dict(
        sorted(found.items(), key=lambda pair: pair[1].lower())
    )


@st.cache_data(ttl=300, show_spinner=False)
def rundown_events(api_key, sport_id, date_text):
    url = f"{TR_BASE}/sports/{sport_id}/events/{date_text}"
    params = {
        "market_ids": "1,2,3",
        "affiliate_ids": "3,19,23",
        "main_line": "true",
        "hide_closed": "true"
    }

    response = requests.get(
        url,
        headers={"X-TheRundown-Key": api_key},
        params=params,
        timeout=25
    )
    response.raise_for_status()
    return response.json()


def show_prematch_odds(sport_id, sport_label):
    st.markdown("### 📊 賽前盤口（TheRundown）")

    api_key = st.secrets.get("THERUNDOWN_API_KEY", "")
    if not api_key:
        st.warning("尚未設定 THERUNDOWN_API_KEY")
        return

    from datetime import datetime

    date_text = datetime.now().strftime("%Y-%m-%d")

    col1, col2 = st.columns([3, 1])
    col1.caption(
        f"{sport_label}｜免費方案｜約 5 分鐘延遲｜賽前全場主盤"
    )

    if col2.button(
        "🔄 更新賽前盤口",
        key=f"refresh_odds_{sport_id}",
        use_container_width=True
    ):
        rundown_events.clear()
        st.rerun()

    try:
        payload = rundown_events(api_key, sport_id, date_text)
    except Exception as e:
        st.error(f"盤口讀取失敗：{e}")
        return

    events = payload.get("events") or []

    if not events:
        st.info("今天尚無符合條件的賽前盤口。")
        return

    def event_label(event):
        teams = event.get("teams") or []
        if isinstance(teams, dict):
            names = [
                str(v.get("name", ""))
                for v in teams.values()
                if isinstance(v, dict)
            ]
        else:
            names = [
                str(t.get("name") or t.get("display_name") or "")
                for t in teams
                if isinstance(t, dict)
            ]

        return " vs ".join(
            [name for name in names if name]
        ) or str(event.get("event_id") or event.get("id") or "未命名賽事")

    labels = [event_label(event) for event in events]
    chosen = st.selectbox(
        "選擇要查看的賽事",
        labels,
        key=f"odds_event_{sport_id}"
    )

    event = events[labels.index(chosen)]
    markets = event.get("markets") or []

    if not markets:
        st.info("此場目前沒有可用的盤口資料。")
        return

    rows = []

    for market in markets:
        mid = market.get("market_id") or market.get("id")
        mname = market.get("name") or {
            1: "勝負",
            2: "讓分",
            3: "大小分"
        }.get(mid, f"市場 {mid}")

        for participant in market.get("participants") or []:
            pname = (
                participant.get("name")
                or participant.get("participant")
                or participant.get("type")
                or "選項"
            )

            for line in participant.get("lines") or []:
                line_val = line.get("line") or line.get("value") or "主盤"

                for price in line.get("prices") or []:
                    book = (
                        price.get("affiliate_name")
                        or price.get("affiliate")
                        or price.get("book")
                        or price.get("sportsbook")
                        or "莊家"
                    )

                    odds = price.get("price") or price.get("odds")

                    if odds is not None:
                        rows.append({
                            "市場": mname,
                            "選項": pname,
                            "盤口": line_val,
                            "莊家": book,
                            "賠率": odds
                        })

    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True
        )
        st.caption("僅顯示 API 實際回傳的盤口與賠率。")
    else:
        st.info("目前沒有可顯示的盤口價格。")
        with st.expander("查看 API 原始資料"):
            st.json(event)

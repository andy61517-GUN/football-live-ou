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
       "affiliate_ids": "19,22,23",
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

    from datetime import datetime, timezone

    date_text = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if st.button("🔄 更新賽前盤口", key=f"refresh_{sport_id}"):
        rundown_events.clear()
        st.rerun()

    try:
        payload = rundown_events(api_key, sport_id, date_text)
    except requests.HTTPError as e:
        st.error(f"API HTTP 錯誤：{e}")
        return
    except Exception as e:
        st.error(f"盤口讀取失敗：{e}")
        return

    events = payload.get("events", [])

    if not events:
        st.warning("目前日期沒有回傳賽事盤口。")
        with st.expander("查看 API 回傳內容"):
            st.json(payload)
        return

    def get_team_names(event):
        teams = event.get("teams", [])
        if isinstance(teams, dict):
            teams = list(teams.values())

        names = []
        for team in teams:
            if isinstance(team, dict):
                names.append(
                    team.get("name")
                    or team.get("display_name")
                    or ""
                )
        return " vs ".join(n for n in names if n)

    labels = [
        get_team_names(e) or str(e.get("event_id", "賽事"))
        for e in events
    ]

    selected = st.selectbox(
        "選擇要查看的賽事",
        labels,
        key=f"event_{sport_id}"
    )

    event = events[labels.index(selected)]
    markets = event.get("markets", [])

    rows = []

    for market in markets:
        market_id = market.get("market_id", market.get("id"))
        market_name = market.get("name", f"市場 {market_id}")

        for participant in market.get("participants", []):
            participant_name = (
                participant.get("name")
                or participant.get("type")
                or "選項"
            )

            for line in participant.get("lines", []):
                line_value = line.get("value", line.get("line", "-"))

                prices = line.get("prices", {})

                if isinstance(prices, dict):
                    price_items = prices.items()
                elif isinstance(prices, list):
                    price_items = [
                        (str(i), p)
                        for i, p in enumerate(prices)
                    ]
                else:
                    continue

                for affiliate_id, price in price_items:
                    if not isinstance(price, dict):
                        continue

                    odds = (
                        price.get("price")
                        or price.get("odds")
                    )

                    affiliate_name = (
                        price.get("affiliate_name")
                        or price.get("name")
                        or {
                            "19": "DraftKings",
                            "22": "BetMGM",
                            "23": "FanDuel"
                        }.get(str(affiliate_id), str(affiliate_id))
                    )

                    if odds is None:
                        continue

                    rows.append({
                        "市場": market_name,
                        "選項": participant_name,
                        "盤口": line_value,
                        "莊家": affiliate_name,
                        "賠率": odds,
                        "更新時間": price.get("updated_at", "未提供")
                    })

    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True
        )
        st.caption(
            "資料來源：TheRundown｜免費方案約延遲 5 分鐘"
        )
    else:
        st.warning("有取得賽事，但目前沒有解析到有效賠率。")
        with st.expander("查看第一場賽事原始資料"):
            st.json(event)
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
# ---------------- 足球走地分析 ----------------

FOOTBALL_BASE = st.secrets.get(
    "FOOTBALL_API_BASE",
    "https://api.5dollarfootballapi.com/v1"
).rstrip("/")

FOOTBALL_KEY = st.secrets.get("FOOTBALL_API_KEY", "")


@st.cache_data(ttl=60, show_spinner=False)
def get_football_live(api_key, base):
    response = requests.get(
        f"{base}/fixtures",
        headers={"Authorization": f"Bearer {api_key}"},
        params={
            "status": "live",
            "per_page": 100
        },
        timeout=25
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, list):
        return data

    return (
        data.get("data")
        or data.get("fixtures")
        or []
    )


@st.cache_data(ttl=60, show_spinner=False)
def get_football_stats(api_key, base, fixture_id):
    response = requests.get(
        f"{base}/fixtures/{fixture_id}/statistics",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict):
        return data.get("data") or data.get("statistics") or []

    return data if isinstance(data, list) else []


def football_page():
    st.header("⚽ 足球即時分析")

    if not FOOTBALL_KEY:
        st.error("尚未設定 FOOTBALL_API_KEY")
        return

    if st.button("🔄 更新足球賽事"):
        get_football_live.clear()
        get_football_stats.clear()
        st.rerun()

    try:
        fixtures = get_football_live(
            FOOTBALL_KEY,
            FOOTBALL_BASE
        )
    except Exception as e:
        st.error(f"足球賽事讀取失敗：{e}")
        return

    if not fixtures:
        st.info("目前沒有取得進行中的足球賽事。")
        return

    # 從實際回傳的比賽整理聯賽
    leagues = {}

    for fixture in fixtures:
        league = fixture.get("league") or {}
        league_id = league.get("id", "unknown")
        league_name = league.get("name", "其他聯賽")

        leagues[str(league_id)] = league_name

    league_options = {
        "全部聯賽": "all"
    }

    for league_id, league_name in sorted(
        leagues.items(),
        key=lambda x: x[1]
    ):
        league_options[league_name] = league_id

    selected_league = st.selectbox(
        "選擇足球聯賽",
        list(league_options.keys())
    )

    selected_id = league_options[selected_league]

    if selected_id != "all":
        fixtures = [
            f for f in fixtures
            if str((f.get("league") or {}).get("id"))
            == selected_id
        ]

    st.caption(f"目前共有 {len(fixtures)} 場符合條件的賽事")

    for fixture in fixtures:
        fixture_id = fixture.get("id")
        home = fixture.get("home") or {}
        away = fixture.get("away") or {}
        league = fixture.get("league") or {}
        goals = fixture.get("goals") or {}
        score = fixture.get("score") or {}
        status = fixture.get("status") or {}

        home_name = home.get("name", "主隊")
        away_name = away.get("name", "客隊")

        home_score = goals.get("home", 0) or 0
        away_score = goals.get("away", 0) or 0

        elapsed = (
            status.get("elapsed")
            or status.get("minute")
            or 0
        )

        with st.expander(
            f"{home_name} {home_score} : "
            f"{away_score} {away_name}｜"
            f"{elapsed}'"
        ):
            st.write(f"聯賽：{league.get('name', '未知聯賽')}")
            st.write(f"比賽時間：{elapsed} 分鐘")

            if not fixture_id:
                st.warning("缺少賽事 ID，無法取得統計。")
                continue

            try:
                stats = get_football_stats(
                    FOOTBALL_KEY,
                    FOOTBALL_BASE,
                    fixture_id
                )

                if not stats:
                    st.info("目前沒有取得球隊統計。")
                    continue

                st.markdown("#### 比賽數據")

                for team_stats in stats:
                    team = team_stats.get("team") or {}
                    team_name = team.get("name", "球隊")

                    st.markdown(f"**{team_name}**")

                    values = team_stats.get("statistics") or []

                    for item in values:
                        st.write(
                            f"{item.get('type', '數據')}："
                            f"{item.get('value', '-')}"
                        )

            except Exception as e:
                st.warning(f"統計資料讀取失敗：{e}")
                # ---------------- NBA 分析 ----------------

NBA_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/scoreboard"
)

NBA_SUMMARY = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/summary"
)


@st.cache_data(ttl=30, show_spinner=False)
def get_nba_games():
    response = requests.get(
        NBA_SCOREBOARD,
        timeout=20
    )
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=30, show_spinner=False)
def get_nba_summary(event_id):
    response = requests.get(
        NBA_SUMMARY,
        params={"event": event_id},
        timeout=20
    )
    response.raise_for_status()
    return response.json()


def nba_page():
    st.header("🏀 NBA 即時分析")

    if st.button("🔄 更新 NBA 賽事"):
        get_nba_games.clear()
        get_nba_summary.clear()
        st.rerun()

    try:
        data = get_nba_games()
    except Exception as e:
        st.error(f"NBA 賽事讀取失敗：{e}")
        return

    events = data.get("events", [])

    if not events:
        st.info("目前沒有 NBA 賽事。")
        return

    options = {}

    for event in events:
        competitors = (
            event.get("competitions", [{}])[0]
            .get("competitors", [])
        )

        names = []
        for team in competitors:
            names.append(
                team.get("team", {}).get("displayName", "未知球隊")
            )

        label = " vs ".join(names) or event.get("name", "NBA 賽事")
        options[label] = event.get("id")

    selected = st.selectbox(
        "選擇 NBA 賽事",
        list(options.keys())
    )

    event_id = options[selected]

    try:
        summary = get_nba_summary(event_id)
    except Exception as e:
        st.error(f"NBA 比賽資料讀取失敗：{e}")
        return

    boxscore = summary.get("boxscore", {})
    teams = boxscore.get("players", [])

    event_data = next(
        (e for e in events if e.get("id") == event_id),
        {}
    )

    competition = (
        event_data.get("competitions", [{}])[0]
    )

    competitors = competition.get("competitors", [])

    current_score = 0
    total_minutes = 48
    elapsed_minutes = 0

    for team in competitors:
        score = team.get("score")
        if score is not None:
            try:
                current_score += int(score)
            except (ValueError, TypeError):
                pass

    status = event_data.get("status", {})
    status_type = status.get("type", {})
    status_name = status_type.get("detail", "未知")

    period = status.get("period", 0)
    clock = status.get("displayClock", "12:00")

    if period:
        try:
            remaining = float(clock)
        except (ValueError, TypeError):
            remaining = 12

        elapsed_minutes = (
            (period - 1) * 12 + (12 - remaining)
        )

    st.markdown(f"### {selected}")
    st.write(f"比賽狀態：{status_name}")
    st.write(f"目前總分：{current_score}")
    st.write(f"節數：第 {period} 節")
    st.write(f"剩餘時間：{clock}")

    if elapsed_minutes > 0:
        remaining_minutes = max(
            total_minutes - elapsed_minutes,
            0
        )

        pace = current_score / elapsed_minutes
        projected_total = (
            current_score + pace * remaining_minutes
        )

        st.markdown("### 📈 全場大小分預估")
        st.metric(
            "預估全場總分",
            f"{projected_total:.1f}"
        )

        st.caption(
            "此數值為目前得分節奏推算，不是實際莊家盤口。"
        )

        line = st.number_input(
            "輸入目前全場大小分盤口",
            min_value=100.0,
            max_value=350.0,
            value=220.5,
            step=0.5
        )

        if st.button("計算 NBA 大小分機率"):
            expected_remaining = max(
                projected_total - current_score,
                0
            )

            over, under, push = ou_probabilities(
                current_score,
                line,
                expected_remaining
            )

            col1, col2, col3 = st.columns(3)
            col1.metric("大分機率", pct(over))
            col2.metric("小分機率", pct(under))
            col3.metric("走水機率", pct(push))

    else:
        st.info("比賽尚未開始，等待開賽後即可進行走地節奏分析。")

    st.markdown("### 📊 NBA 賽前盤口")
    show_prematch_odds(4, "NBA")


# ---------------- 頁面切換 ----------------

if sport_tab == "⚽ 足球":
    football_page()

    st.divider()
    st.subheader("📊 足球賽前盤口")

    api_key = st.secrets.get("THERUNDOWN_API_KEY", "")

    if api_key:
        try:
            soccer_leagues = rundown_soccer_sports(api_key)

            if soccer_leagues:
                league_names = {
                    name: sid
                    for sid, name in soccer_leagues.items()
                }

                selected_name = st.selectbox(
                    "選擇賽前盤口聯賽",
                    list(league_names.keys()),
                    key="prematch_soccer_league"
                )

                show_prematch_odds(
                    league_names[selected_name],
                    selected_name
                )

        except Exception as e:
            st.warning(f"足球聯賽目錄讀取失敗：{e}")

    else:
        st.warning("尚未設定 THERUNDOWN_API_KEY")

else:
    nba_page()

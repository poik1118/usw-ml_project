"""큐 배틀 — 홈. 규칙과 데이터에서 나온 환율표를 보여준다."""

import streamlit as st

st.set_page_config(page_title="큐 배틀", page_icon=":material/swords:", layout="wide")

from shared import engine_or_stop, fmt_plan  # noqa: E402  (set_page_config가 첫 명령이어야 한다)

import core  # noqa: E402



def home() -> None:
    """홈 화면. st.navigation에 callable로 넘겨 사이드바 라벨을 '홈'으로 만든다.

    pages/ 자동 탐색은 파일명을 그대로 메뉴 라벨로 쓴다 — 메인 스크립트가 `app`으로
    떠서 어색했다. st.navigation을 쓰면 **파일 구조는 그대로 두고** 라벨·아이콘만
    지정할 수 있다. url_path는 기존 주소를 유지하려고 명시한다.
    """
    # 제목·부제는 엔진보다 먼저 그린다. 느린 계산을 앞에 두면 화면이 한참
    # 반쯤 그려진 채로 남아 "테마가 깨진 것처럼" 보인다 (측정: 첫 로드 9초).
    st.title("줴줴이야", text_alignment="center")
    st.markdown(
        "#### 다이아~마스터 구간 **9,879 경기**로 학습한 승패 예측 모델\n"
        "**채팅을 통한 1분 대결**",
        text_alignment="center",
    )

    engine = engine_or_stop()
    st.markdown(
        ":gray-badge[:material/database: 9,879경기] "
        f":blue-badge[:material/target: AUC {engine.auc:.4f}] "
        f":yellow-badge[:material/timer: {int(core.DURATION)}초] "
        f":violet-badge[:material/keyboard: 명령어 {len(core.COMMANDS)}종] "
        ":green-badge[:material/devices: PC/Mobile]",
        text_alignment="center",
    )
    st.space("medium")

    nav = st.container(horizontal=True, horizontal_alignment="center")
    nav.page_link("pages/3_1대1_대결.py", label="**대결 시작**", icon=":material/swords:")
    nav.page_link("pages/2_시뮬레이터.py", label="시뮬레이터", icon=":material/tune:")
    nav.page_link("pages/1_데이터_탐색.py", label="데이터 탐색", icon=":material/analytics:")
    st.space("medium")

    # 5주차 갤러리 시연은 슬라이드를 넘길 손이 없다 — 문제·대상·Must 3개를 홈 첫 화면에 둔다
    with st.container(border=True):
        st.markdown(
            "**문제** — 롤 초반 지표를 **감으로** 판단한다. 전적 사이트는 끝난 경기의 결과값만 보여주고, "
            "\"드래곤이 중요하다\"는 말에는 **몇 %p인지가 없다.**\n\n"
            "**대상** — 초반 지표(골드·킬·CS·오브젝트)를 읽을 줄 아는 플레이어\n\n"
            "**Must 3개** — ① **승률 분해**: 지표 차이 → 승률과 항별 기여 %p (시뮬레이터) · "
            "② **데이터 근거**: 타워 계수가 왜 음수인지 원본 9,879경기에서 확인 (데이터 탐색) · "
            "③ **60초 1대1 대결**: 채팅 명령으로 승률 줄다리기"
        )
    st.space("medium")

    # ── 규칙 ──────────────────────────────────────────────────────────────
    st.header("규칙", divider="gray")
    r1, r2 = st.columns(2, gap="medium")
    with r1.container(border=True):
        st.markdown("##### :material/bolt: 입력은 즉시, 큐로 쌓인다")
        st.markdown(
            f"입력은 **FIFO 큐**에 쌓이고 **{core.SEC}초에 하나씩** 처리된다.\n\n"
            f"측정된 서버 하한 {core.MIN_GAP}초 바로 위라 대부분 즉시 반영된다"
        )
    with r2.container(border=True):
        st.markdown("##### :material/hourglass_top: 쿨타임이 전략의 축")
        st.markdown(
            "실제 LOL의 재사용 대기시간을 바탕으로 조정 환산해 넣었다.\n\n"
            f"**드래곤 {engine.spawn['dragon']:.0f}초**(5:00) · **전령 {engine.spawn['herald']:.0f}초**(8:00)에 등장한다. "
        )
    r3, r4 = st.columns(2, gap="medium")
    with r3.container(border=True):
        st.markdown("##### :material/trending_down: 완성 전까지는 손해")
        st.markdown(
            "일부 명령은 **여러 번** 쳐야 완성된다.\n\n"
            "예시: `tower`는 5타인데 **1~4타는 승률이 내려가고 5타에 터진다.**\n\n"
            f"**{int(core.DURATION)}초가 끝나면 큐에 남은 것은 전부 소멸한다.**"
        )
    with r4.container(border=True):
        st.markdown("##### :material/local_fire_department: 막타를 가져간 쪽만")
        st.markdown(
            "드래곤·전령·퍼블은 **공유 체력**이다.\n\n서로 체력을 공유하지만 **막타를 넣은 쪽이** 가져간다.\n\n"
        )
    st.caption(
        f"게임 {int(core.DURATION)}초 = 실제 10분. **시간 압축 {core.COMPRESS:.0f}:1** 이라 쿨타임·스폰이 그대로 환산된다."
    )

    # ── 명령어 ────────────────────────────────────────────────────────────
    st.header("명령어", divider="gray")
    st.caption(
        "**값은 전부 데이터에서 나왔다.** 자기계수는 로지스틱 회귀 계수, 골드·경험은 1차 회귀 "
        "측정값, 쿨타임은 10분 평균 빈도, 캡은 데이터 관측 범위다. 설계로 정한 건 `N타` 하나뿐이다."
    )

    rows = []
    for cmd in sorted(core.COMMANDS, key=lambda x: -engine.efficiency(x)):
        spec = core.COMMANDS[cmd]
        g, e = engine.reward[cmd]
        own = engine.coef.get(spec["feature"], 0.0) if spec["feature"] else 0.0
        cd = engine.cooldown.get(cmd, 0.0)
        rows.append({
            "명령어": cmd,
            "타수": len(cmd) + 1,
            "N타": spec["n"],
            "쿨타임": f"{cd:.2f}초" if cd else "—",
            "스폰": f"{engine.spawn[cmd]:.0f}초" if cmd in engine.spawn else "—",
            "자기계수": round(own, 5),
            "골드": round(g, 1),
            "경험": round(e, 1),
            "순 logit": round(engine.net_logit(cmd), 5),
            "효율/초": round(engine.efficiency(cmd), 4),
            "캡": engine.unit_cap[cmd],
            "선점": "O" if spec["contested"] else "",
            "유틸": {"ward": f"시야 {core.WARD_DURATION:.0f}초 · 기습 방어",
                     core.DISRUPTOR: f"와드 제거 또는 기습({core.FREEZE}초 정지)"}.get(cmd, ""),
        })
    st.dataframe(rows, hide_index=True, height=420)

    c1, c2 = st.columns(2, gap="medium")
    with c1.container(border=True):
        st.markdown("##### :material/swap_vert: 자기계수가 음수인 명령 5개")
        st.markdown(
            "`tower` `kill` `cs` `jungle` (+ `ward` ≈0) — **원본 데이터에서 실제로 음수**다. "
            "골드의 대리변수라서 골드차를 통제하면 부호가 뒤집힌다 "
            "(단독 상관은 전부 양수). **숨기지 않고 그대로 쓴다.**"
        )
    with c2.container(border=True):
        st.markdown("##### :material/dangerous: 정직한 함정")
        st.markdown(
            f"`ward` 순 logit **{engine.net_logit('ward'):+.5f}**, "
            f"`wardkill` **{engine.net_logit('wardkill'):+.5f}**. "
            "데이터가 '효과 없다'고 말하므로 게임에서도 함정이다 — "
            "대신 이를 운영 변수(**시야·기습 유틸리티**)로 보완했다."
        )

    # ── 엔진 ──────────────────────────────────────────────────────────────
    st.header("승률 엔진", divider="gray")
    st.latex(r"P(\text{승}) = \sigma\!\left(\sum_{f} \beta_f \cdot \Delta f\right)")
    with st.expander("학습된 계수 보기", icon=":material/function:"):
        st.code(
            "\n".join(
                [f"β[{f}] = {engine.coef[f]:+.7f}" for f in core.FEATURES]
                + ["", f"절편 = {engine.intercept:+.8f}   ← 미러 증강으로 정확히 0",
                   f"축 캡: goldDiff ±{engine.axis_cap['goldDiff']:.0f} / "
                   f"expDiff ±{engine.axis_cap['expDiff']:.0f}  (데이터 99분위)"]
            ),
            language="text",
        )
    st.caption(
        "블루/레드 라벨은 임의이므로 부호를 뒤집은 사본을 학습에 더했다(미러 증강). "
        "덕분에 절편이 정확히 0이 되어 **P(나) + P(상대)가 항상 100%** 다."
    )

    seq = core.suggest_sequence(engine)
    st.markdown(f"**추천 순서** ({len(seq)}타) — {fmt_plan(seq)}")
    st.caption(
        "쿨타임이 생긴 뒤로는 '몇 개씩'이 아니라 **언제 치느냐**가 전략이다. "
    )


PAGES = [
    st.Page(home, title="홈", icon=":material/home:", url_path="home", default=True),
    st.Page("pages/1_데이터_탐색.py", title="데이터 탐색",
            icon=":material/analytics:", url_path="데이터_탐색"),
    st.Page("pages/2_시뮬레이터.py", title="시뮬레이터",
            icon=":material/tune:", url_path="시뮬레이터"),
    st.Page("pages/3_1대1_대결.py", title="1대1 대결",
            icon=":material/swords:", url_path="1대1_대결"),
]
st.navigation(PAGES).run()

"""화면 2 — 시뮬레이터. 쿨타임·스폰을 쥐고 전략을 짜 보는 공간."""

import streamlit as st

import core
from shared import engine_or_stop, fmt_plan, level_color

st.title("시뮬레이터", text_alignment="center")
st.caption("대결 전에 여기서 연습한다. 타자 속도를 바꾸면 최적 전략이 바뀐다.",
           text_alignment="center")

engine = engine_or_stop()
gc = int(engine.axis_cap["goldDiff"])
ec = int(engine.axis_cap["expDiff"])

tab_speed, tab_slider, tab_cmd = st.tabs(["전략 시나리오", "상태 슬라이더", "명령어 하나 파보기"])

# ------------------------------------------------------------------ 타자 속도
with tab_speed:
    st.subheader("예시 전략 시나리오")
    kpm = st.slider("타자 속도 (타/분)", 100, 600, 300, step=25,
                    help="명령어마다 글자 수가 다르다. cs는 3타, firstblood는 11타.")
    strat = st.selectbox("전략", ["정석(쿨타임순)", "킬사이클", "타워러시", "오브젝트선점",
                                 "골드몰빵", "레벨몰빵", "짧은단어", "시야전략"])

    def build(name: str) -> list[str]:
        n_kill, n_tower = core.COMMANDS["kill"]["n"], core.COMMANDS["tower"]["n"]
        if name == "정석(쿨타임순)":
            return core.suggest_sequence(engine)
        if name == "킬사이클":
            return [c for _ in range(7) for c in ["kill"] * n_kill + ["gold"] * 12]
        if name == "타워러시":
            return ["tower"] * (4 * n_tower) + ["gold"] * 300
        if name == "오브젝트선점":
            return (["gold"] * 48 + ["dragon"] * core.COMMANDS["dragon"]["n"]
                    + ["gold"] * 40 + ["herald"] * core.COMMANDS["herald"]["n"] + ["gold"] * 200)
        if name == "짧은단어":
            cheap = sorted(core.COMMANDS, key=lambda c: len(c))[:4]
            return [cheap[i % len(cheap)] for i in range(400)]
        if name == "시야전략":
            return ["ward", "wardkill"] * 100
        return [{"골드몰빵": "gold", "레벨몰빵": "level"}[name]] * 400

    seq = build(strat)
    # 지터 없이 균등하게 친다고 가정 — 시뮬레이터는 결정론적이어야 비교가 된다
    presses, t = [], 0.0
    for cmd in seq:
        t += (len(cmd) + 1) / (kpm / 60.0)
        if t >= core.DURATION:
            break
        presses.append((cmd, t))
    presses, limited = core.rate_limit(presses)
    r = core.battle(presses, [], engine)
    side = r["side1"]

    c = st.container(horizontal=True)
    c.metric("칠 수 있는 명령 수", len(presses), border=True)
    c.metric("완성한 단위", len(side.units), border=True)
    c.metric("승률", f"{r['p1']['score']}%", border=True)
    st.progress(r["p1"]["score"] / 100)

    by_reason: dict[str, int] = {}
    for _cmd, why, _t in side.rejected:
        by_reason[why] = by_reason.get(why, 0) + 1
    if by_reason:
        st.caption("거부 사유: " + " · ".join(f"{k} {v}회" for k, v in by_reason.items()))
    if limited:
        st.caption(f":orange[레이트 리밋으로 {len(limited)}회 거부 — 서버 하한 {core.MIN_GAP}초]")

    st.write("**완성 내역**: " + (fmt_plan([c2 for c2, _ in side.units]) or "없음"))
    for why in r["p1"]["reasons"]:
        st.write(f"- {why}")

    st.space("medium")
    st.subheader("속도를 바꾸면 승률이 어떻게 변하나")
    curve = []
    for k in range(150, 601, 50):
        pr, tt = [], 0.0
        for cmd in seq:
            tt += (len(cmd) + 1) / (k / 60.0)
            if tt >= core.DURATION:
                break
            pr.append((cmd, tt))
        pr, _ = core.rate_limit(pr)
        curve.append({"타/분": k, "승률": core.battle(pr, [], engine)["p1"]["score"]})
    st.line_chart({"승률": [x["승률"] for x in curve]})
    st.caption(f"x축은 150~600 타/분 (50단위). 전략: {strat}")

# ------------------------------------------------------------------ 슬라이더
def diff_slider(label: str, cap: int, step: int = 1) -> int:
    """`Blue − Red` 차이 슬라이더. **왼쪽으로 갈수록 Blue(=나)의 차이값이 커진다.**

    왼쪽이 곧 '유리'는 **아니다** — 계수가 음수인 피처는 반대로 간다. 아래 탭 캡션 참고.

    `st.slider`는 항상 왼쪽이 최솟값이라 방향을 뒤집을 수 없다. `st.select_slider`는
    옵션을 **준 순서대로 왼쪽→오른쪽** 에 깔므로, 내림차순(+cap … 0 … −cap)으로
    주면 왼쪽 끝이 `Blue +cap`이 된다. 표시되는 숫자는 `format_func`로 실제 값을 쓴다.
    """
    top = (cap // step) * step                      # 0이 눈금에 정확히 들어오게 맞춘다
    options = list(range(top, -top - 1, -step))
    return st.select_slider(
        label, options=options, value=0,
        # 0(차이 없음)일 때는 아무것도 띄우지 않는다. 움직이면 누가 앞서는지만 보여준다.
        format_func=lambda v: f"Blue +{v:,}" if v > 0 else (f"Red +{-v:,}" if v < 0 else ""),
    )


with tab_slider:
    # 이 탭은 **골드·경험을 따로 고정해 두고** 묻는다 = 회귀가 보는 것과 똑같은 조건부
    # 질문이다. 그래서 계수가 음수인 피처는 왼쪽(내 차이값 ↑)이 오히려 불리하게 나온다.
    # 버그가 아니라 이 탭의 존재 이유다. 대결 화면은 골드를 같이 주므로 직관대로 움직인다.
    neg = [cmd for cmd, s in core.COMMANDS.items()
           if s["feature"] and engine.coef[s["feature"]] < 0]
    st.caption(
        f"**골드·경험을 고정한 채 한 피처만 움직이는 '조건부' 탐색기다.** "
        f"축 범위는 데이터 99분위다 — 골드 ±{gc:,} / 경험 ±{ec:,}"
    )
    st.info(
        f"**왼쪽이 항상 유리한 게 아니다.** 계수가 음수인 "
        f"**{' · '.join(neg)}** 는 왼쪽으로 밀면 승률이 **내려간다.**\n\n"
        f"예: `tower`를 Blue +1로 밀면 모델에게는 *\"타워를 1개 더 깼는데 골드는 똑같다\"* "
        f"= *\"타워 말고는 {engine.reward['tower'][0]:,.0f}골드만큼 다 밀렸다\"* 로 읽힌다. "
        f"타워가 나쁜 게 아니라, **타워가 주는 골드를 이 탭에서는 안 줬을 뿐**이다 — "
        f"골드 슬라이더를 같이 왼쪽으로 밀면 부호가 뒤집힌다. "
        f"단독 상관은 {' · '.join(neg)} 전부 양수다.",
        icon=":material/functions:",
    )
    with st.sidebar:
        st.subheader("Blue (`player`) − Red")
        st.caption("◀ 왼쪽 = Blue의 차이값 ↑ · 오른쪽 = Red의 차이값 ↑ ▶")
        gold = diff_slider("골드", gc, 50)
        exp = diff_slider("경험치", ec, 50)
        counts: dict[str, int] = {}
        for cmd, spec in core.COMMANDS.items():
            f = spec["feature"]
            if f is None:
                continue
            # 음수 계수에 표식을 붙인다 — 슬라이더를 만지는 순간 이유를 알 수 있어야 한다
            sign = " ⊖" if engine.coef[f] < 0 else ""
            counts[f] = diff_slider(f"{cmd} ({f}){sign}", engine.unit_cap[cmd])
        st.caption("⊖ = 계수 음수. 골드를 고정하면 왼쪽이 불리하게 나온다.")

    mine = core.Side(gold=max(gold, 0.0), exp=max(exp, 0.0),
                     counts={f: v for f, v in counts.items() if v > 0})
    theirs = core.Side(gold=max(-gold, 0.0), exp=max(-exp, 0.0),
                       counts={f: -v for f, v in counts.items() if v < 0})
    result = core.win_rate(engine, mine, theirs)
    blue = result["score"]
    st.markdown(f"## :{level_color(blue)}[Blue {blue}%] — {result['level']}")
    # 대결 화면의 줄다리기 바와 같은 방향이다 (왼쪽이 나)
    st.progress(blue / 100, text=f"Blue {blue}%  ◀——▶  {100 - blue}% Red")
    st.caption("선형 모델이라 각 항의 기여가 정확히 분해된다. SHAP이 필요 없다.")
    for why in result["reasons"]:
        st.write(f"- {why}")
    if abs(gold) >= gc - 50 or abs(exp) >= ec - 50:
        st.warning("축이 데이터 99분위에 닿았다. 이 지점을 넘는 입력은 모델에 묻지 않는다.",
                   icon=":material/warning:")

# ------------------------------------------------------------------ 명령어
with tab_cmd:
    cmd = st.segmented_control("명령어", list(core.COMMANDS), default="tower")
    if cmd:
        spec = core.COMMANDS[cmd]
        n = spec["n"]
        cd = engine.cooldown.get(cmd, 0.0)
        c = st.container(horizontal=True)
        c.metric("타수", f"{len(cmd) + 1}타", border=True)
        c.metric("N타 완성", n, border=True)
        c.metric("쿨타임", f"{cd:.2f}초" if cd else "없음", border=True)
        c.metric("스폰", f"{engine.spawn.get(cmd, 0.0):.0f}초", border=True)
        c.metric("순 logit", f"{engine.net_logit(cmd):+.5f}", border=True)
        if cmd == "ward":
            st.info(f"**시야 {core.WARD_DURATION:.0f}초** — 상대 큐가 보이고, "
                    f"와드가 살아 있는 동안 **기습당하지 않는다.**",
                    icon=":material/visibility:")
        if cmd == core.DISRUPTOR:
            st.info(f"상대에게 와드가 있으면 **와드 1개만 걷어낸다**. 와드가 없으면 "
                    f"**기습 성공 — 상대를 {core.FREEZE}초간 입력 불가**로 만든다.",
                    icon=":material/flash_on:")

        st.subheader("연타했을 때 승률 궤적")
        traj = []
        for k in range(1, 31):
            start = engine.spawn.get(cmd, 0.0) + 0.1
            presses = [(cmd, start + i * (core.SEC + 0.05)) for i in range(k)]
            traj.append(core.battle(presses, [], engine)["p1"]["score"])
        st.line_chart({"승률": traj})
        st.caption(
            f"{n}타마다 보상이 터진다. 자기계수가 음수면 그 사이 승률이 내려간다."
            if n > 1 else "1타에 완성된다. 완성 실패 위험이 없다."
        )
        if cd:
            st.caption(f"쿨타임 {cd:.2f}초 때문에 연타해도 {int(core.DURATION / cd) + 1}회가 한계다.")

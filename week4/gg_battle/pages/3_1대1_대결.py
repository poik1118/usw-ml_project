"""화면 3 — 1대1 큐 배틀. 두 기기가 같은 방에 들어와 동시에 플레이한다.

상태 공유 — **각자 자기 파일만 쓴다.** 동시 쓰기 경합이 구조적으로 불가능하다.
    room.json      초대(invite) 시각 · 게임 길이     ← 신청한 쪽이 쓴다
    accept_P1.json / accept_P2.json                 ← 각자 자기 것만 쓴다
    p1.jsonl / p2.jsonl                             ← 각자 자기 것만 append

시작 시각은 **아무도 쓰지 않는다.** 양쪽 수락 시각에서 `max(수락) + COUNTDOWN`으로
각자 계산한다 — 같은 파일에서 같은 값이 나오므로 추가 동기화 쓰기가 필요 없다.

경기 판정은 전부 '입력 시각' 기준 계산이라 폴링이 0.5초 늦어도 결과가 바뀌지 않는다.
"""

import json
import time
from pathlib import Path

import streamlit as st

import core
from shared import engine_or_stop, level_color

RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
ROOM = RUNTIME / "room.json"
SLOTS = {"P1": RUNTIME / "p1.jsonl", "P2": RUNTIME / "p2.jsonl"}
ACCEPT = {"P1": RUNTIME / "accept_P1.json", "P2": RUNTIME / "accept_P2.json"}
COUNTDOWN = 3.0          # 양쪽 수락 후 시작까지 (롤 매칭 수락 뒤 로딩에 해당)

st.title("1대1 대결", text_alignment="center")
engine = engine_or_stop()
RUNTIME.mkdir(exist_ok=True)


# ----------------------------------------------------------------- 파일 I/O
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def read_presses(slot: str) -> list[tuple[str, float]]:
    path = SLOTS[slot]
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            d = json.loads(line)
            out.append((d["cmd"], float(d["t"])))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue        # 반쯤 쓰인 줄은 다음 폴링에 다시 읽힌다
    return out


def append_press(slot: str, cmd: str, t: float) -> None:
    """O_APPEND 한 줄 쓰기. 자기 파일만 쓰므로 경합이 없다."""
    with SLOTS[slot].open("a") as f:
        f.write(json.dumps({"cmd": cmd, "t": round(t, 3)}) + "\n")


def invite(duration: float = core.DURATION) -> None:
    """대결 신청 — 새 invite를 열고 이전 수락·입력을 전부 지운다."""
    for p in [*SLOTS.values(), *ACCEPT.values()]:
        p.unlink(missing_ok=True)
    ROOM.write_text(json.dumps({"invite": time.time(), "duration": duration}))


def accept(slot: str, invite_id: float) -> None:
    """수락 — 자기 파일만 쓴다."""
    ACCEPT[slot].write_text(json.dumps({"invite": invite_id, "at": time.time()}))


def clear_all() -> None:
    for p in [ROOM, *SLOTS.values(), *ACCEPT.values()]:
        p.unlink(missing_ok=True)


def read_state() -> dict:
    """현재 방 상태를 **파일에서만** 계산한다. 양쪽이 같은 값을 얻는다.

    phase: idle(신청 전) → lobby(수락 대기) → countdown → playing → over
    """
    room = _read_json(ROOM)
    inv = room.get("invite")
    duration = float(room.get("duration", core.DURATION))
    if inv is None:
        return {"phase": "idle", "invite": None, "duration": duration,
                "accepted": {}, "started_at": None}

    accepted = {}
    for slot, path in ACCEPT.items():
        a = _read_json(path)
        if a.get("invite") == inv:
            accepted[slot] = float(a["at"])

    if len(accepted) < 2:
        return {"phase": "lobby", "invite": inv, "duration": duration,
                "accepted": accepted, "started_at": None}

    started = max(accepted.values()) + COUNTDOWN       # 아무도 쓰지 않는 유도값
    now = time.time()
    phase = ("countdown" if now < started
             else "playing" if now < started + duration else "over")
    return {"phase": phase, "invite": inv, "duration": duration,
            "accepted": accepted, "started_at": started}


# ----------------------------------------------------------------- 내 자리
if "slot" not in st.session_state:
    st.session_state.slot = "P1"
if "last_input" not in st.session_state:
    st.session_state.last_input = -1e9

top = st.container(horizontal=True)
with top:
    st.session_state.slot = st.segmented_control(
        "내 자리", ["P1", "P2"], default=st.session_state.slot, key="slot_pick"
    ) or st.session_state.slot
me = st.session_state.slot
foe = "P2" if me == "P1" else "P1"

state = read_state()
phase, duration = state["phase"], state["duration"]
started = state["started_at"]

# 상단 슬롯은 **st.stop 없이 항상** 만든다. 만들지 않은 채 run_every fragment가
# 살아 있으면 "container was not written to during the initial run"으로 터진다
# (초기화 직후 재현됨). .empty()로 자리만 확보한다 — 실제 쓰기로는 안 된다.
head_slot = st.empty()
head_slot.empty()


# ----------------------------------------------------------------- 로비
def lobby() -> None:
    """롤 매칭 수락 창. 양쪽이 수락해야 시작한다."""
    acc = state["accepted"]
    if phase == "idle":
        st.info("**대결 신청**을 누르면 상대에게 수락 요청이 간다. 두 기기 중 아무나 눌러도 된다.",
                icon=":material/sports_esports:")
        if st.button("대결 신청", icon=":material/person_add:", type="primary"):
            invite()
            st.rerun()
        return

    st.markdown("### 대결 수락", text_alignment="center")
    st.markdown(f"#### {len(acc)} / 2 수락", text_alignment="center")
    cols = st.container(horizontal=True, horizontal_alignment="center")
    for slot in ("P1", "P2"):
        box = cols.container(border=True, width=200)
        box.markdown(f"##### {slot}" + (" (나)" if slot == me else ""))
        if slot in acc:
            box.markdown(":green-badge[:material/check_circle: 수락 완료]")
        else:
            box.markdown(":orange-badge[:material/hourglass_top: 대기 중]")

    st.space("small")
    btns = st.container(horizontal=True, horizontal_alignment="center")
    if me in acc:
        btns.button("수락 완료", icon=":material/check:", disabled=True)
    elif btns.button("수락", icon=":material/check_circle:", type="primary"):
        accept(me, state["invite"])
        st.rerun()
    if btns.button("취소", icon=":material/close:"):
        clear_all()
        st.rerun()
    st.caption(f"양쪽이 수락하면 {COUNTDOWN:.0f}초 뒤 시작한다.", text_alignment="center")


# ----------------------------------------------------------------- 입력
def _sides(now: float):
    a, b, hp = core.simulate(
        [(c, t) for c, t in read_presses("P1") if t <= now],
        [(c, t) for c, t in read_presses("P2") if t <= now],
        engine, duration)
    return (a, b, hp) if me == "P1" else (b, a, hp)


@st.fragment
def input_panel() -> None:
    """입력 전용. run_every를 **걸지 않는다** — 걸면 타이핑이 날아간다(측정 확인)."""
    now = time.time() - started
    if now >= duration:
        return
    mine_side, foe_side, hp = _sides(now)
    if now < mine_side.frozen_until:
        st.error(f"기습당했다 — {mine_side.frozen_until - now:.1f}초 뒤 입력 가능",
                 icon=":material/flash_off:")

    def submit(cmd: str) -> None:
        wall = time.time()
        t_rel = wall - started
        if t_rel >= duration:
            st.toast("시간 종료", icon=":material/timer_off:")
            return
        if wall - st.session_state.last_input < core.MIN_GAP:
            st.toast(f"너무 빠르다 ({core.MIN_GAP}초 간격 필요)", icon=":material/speed:")
            return
        ok, why = core.available(engine, mine_side, foe_side, cmd, t_rel, hp)
        if not ok:
            st.toast(f"{cmd}: {why}", icon=":material/block:")
            return
        st.session_state.last_input = wall
        append_press(me, cmd, t_rel)

    st.markdown("##### :material/touch_app: 탭해서 입력")
    st.caption("회색 버튼은 쿨타임·스폰 대기 중이다. 눌러보면 사유를 알려준다.")
    order = sorted(core.COMMANDS, key=lambda c: -engine.efficiency(c))
    for chunk in (order[:4], order[4:8], order[8:]):
        row = st.container(horizontal=True)
        for cmd in chunk:
            ok, _why = core.available(engine, mine_side, foe_side, cmd, now, hp)
            n = core.COMMANDS[cmd]["n"]
            label = cmd + (f" ×{n}" if n > 1 else "")
            # 비활성화하지 않는다 — 쿨타임이 풀려도 fragment가 다시 그려질 때까지
            # 못 누르게 되기 때문이다. 누르면 submit이 사유를 토스트로 알려준다.
            if row.button(label, key=f"btn_{cmd}", type="primary" if ok else "secondary"):
                submit(cmd)
                st.rerun(scope="fragment")

    typed = st.chat_input("명령어를 직접 입력 (gold, tower, dragon ...)", key="cmd_input")
    if typed:
        cmd = typed.strip().lower()
        if cmd not in core.COMMANDS:
            st.toast(f"없는 명령어: {cmd}", icon=":material/error:")
        else:
            submit(cmd)
        st.rerun(scope="fragment")


def scoreboard(r: dict) -> None:
    st.markdown("##### :material/leaderboard: 스코어보드")
    cols = st.container(horizontal=True)
    for slot, res, side in (("P1", r["p1"], r["side1"]), ("P2", r["p2"], r["side2"])):
        box = cols.container(border=True)
        box.markdown(f"### {slot}" + (" (나)" if slot == me else ""))
        box.markdown(f"# :{level_color(res['score'])}[{res['score']}%]")
        box.markdown(f":{level_color(res['score'])}-badge[{res['level']}]")
        box.markdown(f":yellow-badge[:material/paid: 골드 {side.gold:,.0f}] "
                     f":blue-badge[:material/school: 경험 {side.exp:,.0f}]")
        done: dict[str, int] = {}
        for c, _ in side.units:
            done[c] = done.get(c, 0) + 1
        box.write("완성: " + (" · ".join(f"{k}×{v}" for k, v in done.items()) or "없음"))
        if side.stolen:
            box.caption(f":red[스틸당함: {' · '.join(side.stolen)}]")
        for why in res["reasons"][:4]:
            box.write(f"- {why}")
        by_reason: dict[str, int] = {}
        for _cmd, reason, _t in side.rejected:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        if by_reason:
            box.caption(":orange[거부: " + " · ".join(f"{k} {v}" for k, v in by_reason.items()) + "]")


# ----------------------------------------------------------------- 라이브 감시
@st.fragment(run_every="1s")
def watcher() -> None:
    """방 상태를 폴링한다. 역할이 두 가지다.

    1. **양쪽 동기화** — 상대가 신청·수락·취소하면 phase가 바뀌고, 그때
       전체 재실행을 걸어 화면을 전환한다. (예전에는 started_at을 스크립트
       실행 시점에 한 번만 읽어서, 상대가 새 게임을 시작해도 내 쪽은 옛 시각을 썼다.)
    2. **라이브 숫자** — 남은 시간·승률·쿨타임을 head_slot에 그린다.
       입력 위젯은 넣지 않는다 (주기 재실행이 타이핑을 날린다).

    주기는 1초다. 0.5초로 하면 **2세션이 동시에 폴링할 때** 서버가 못 따라가
    metric·progress·chat_input이 회색 스켈레톤으로 남는다 (실측 확인).
    """
    s = read_state()
    # phase뿐 아니라 **수락 현황**도 비교한다. 로비 안에서 상대가 수락하면
    # phase는 그대로 lobby라서, phase만 보면 "1/2 수락"이 갱신되지 않는다.
    if ((s["phase"], s["invite"], sorted(s["accepted"]))
            != (phase, state["invite"], sorted(state["accepted"]))):
        st.rerun()                      # 화면 전환·갱신이 필요하다 → 전체 재실행

    if s["phase"] == "countdown":
        with head_slot.container():
            st.markdown(f"# {s['started_at'] - time.time():.0f}", text_alignment="center")
            st.markdown("### 곧 시작", text_alignment="center")
        return
    if s["phase"] != "playing" or started is None:
        return

    now = time.time() - started
    left = max(0.0, duration - now)
    cut = min(now, duration)
    r = core.battle([(c, t) for c, t in read_presses("P1") if t <= cut],
                    [(c, t) for c, t in read_presses("P2") if t <= cut],
                    engine, duration=cut if left > 0 else duration)
    mine_side, foe_side = (r["side1"], r["side2"]) if me == "P1" else (r["side2"], r["side1"])

    with head_slot.container():
        head = st.container(horizontal=True)
        head.metric("P1" + (" (나)" if me == "P1" else ""), f"{r['p1']['score']}%",
                    border=True, delta="LEAD" if r["p1"]["score"] > 50 else None)
        head.metric("남은 시간", f"{left:.0f}", border=True, delta_description="초")
        head.metric("P2" + (" (나)" if me == "P2" else ""), f"{r['p2']['score']}%",
                    border=True, delta="LEAD" if r["p2"]["score"] > 50 else None)
        st.progress(r["p1"]["score"] / 100,
                    text=f"P1 {r['p1']['score']}%  ◀——▶  {r['p2']['score']}% P2")
        st.markdown(
            f":gray-badge[:material/pending: 큐 {mine_side.in_system(now)}/{core.QUEUE_CAP}] "
            f":blue-badge[:material/visibility: 내 와드 {mine_side.live_wards(now)}] "
            f":gray-badge[상대 와드 {foe_side.live_wards(now)}] "
            + (":green-badge[:material/visibility: 시야 확보]"
               if mine_side.has_vision(now) else ":red-badge[:material/visibility_off: 장님]")
        )
        if now < mine_side.frozen_until:
            st.error(f"정지 {mine_side.frozen_until - now:.1f}초", icon=":material/flash_off:")

        st.caption("경합 오브젝트 — 막타를 넣은 쪽만 가져간다")
        obj = st.container(horizontal=True)
        for cmd, spec in core.COMMANDS.items():
            if not spec["contested"]:
                continue
            full, left_hp = spec["n"], r["hp"].get(cmd, 0)
            if now < engine.spawn.get(cmd, 0.0):
                obj.metric(cmd, f"{engine.spawn[cmd] - now:.0f}s", border=True,
                           delta_description="후 등장")
            elif left_hp <= 0:
                owner = "나" if mine_side.counts.get(spec["feature"], 0) else "상대"
                obj.metric(cmd, f"{owner} 획득", border=True,
                           delta="스틸당함" if cmd in mine_side.stolen else None,
                           delta_color="inverse")
            else:
                mh, fh = mine_side.hits.get(cmd, 0), foe_side.hits.get(cmd, 0)
                obj.metric(f"{cmd} {'◆' * left_hp}{'◇' * (full - left_hp)}",
                           f"{left_hp}/{full}", border=True,
                           delta=f"나 {mh} : {fh} 상대" if (mh or fh) else None,
                           delta_color="off")
        clutch = [c for c, v in r["hp"].items()
                  if v == 1 and core.COMMANDS[c]["n"] > 1 and now >= engine.spawn.get(c, 0.0)]
        if clutch:
            st.warning(f"{' · '.join(clutch)} 막타 한 대 남았다!", icon=":material/bolt:")

        waiting = []
        for cmd in core.COMMANDS:
            ok, why = core.available(engine, mine_side, foe_side, cmd, now, r["hp"])
            if ok:
                continue
            if why == core.R_COOLDOWN:
                waiting.append(f"{cmd} {mine_side.remaining_cd(cmd, now):.1f}s")
            elif why == core.R_SPAWN:
                waiting.append(f"{cmd} {engine.spawn[cmd] - now:.0f}s 후")
            else:
                waiting.append(f"{cmd} ({why})")
        st.caption("대기 중: " + (" · ".join(waiting) if waiting else "전부 사용 가능"))
        if mine_side.has_vision(now):
            recent = [c for c, _ in foe_side.units[-5:]]
            st.caption(f":green[시야] 상대 큐 {foe_side.in_system(now)}개 · "
                       f"최근 완성: {' · '.join(recent) if recent else '없음'}")


# ----------------------------------------------------------------- 화면 분기
st.caption(
    f"당신은 **{me}** · 다른 기기에서 **{foe}** 를 고르면 같은 방에서 대결한다. "
    "휴대폰도 된다 (같은 계정으로 로그인한 브라우저).",
    text_alignment="center",
)

if phase in ("idle", "lobby"):
    lobby()
elif phase == "countdown":
    st.markdown("### 수락 완료 — 곧 시작", text_alignment="center")
    if st.button("취소", icon=":material/close:"):
        clear_all()
        st.rerun()
else:
    ctl = st.container(horizontal=True)
    if ctl.button("다시 대결", icon=":material/replay:"):
        invite()
        st.rerun()
    if ctl.button("방 비우기", icon=":material/restart_alt:"):
        clear_all()
        st.rerun()

    if phase == "playing":
        input_panel()
    else:
        st.success("시간 종료", icon=":material/flag:")

    st.space("medium")
    cut = duration if phase == "over" else min(time.time() - started, duration)
    result = core.battle([(c, t) for c, t in read_presses("P1") if t <= cut],
                         [(c, t) for c, t in read_presses("P2") if t <= cut],
                         engine, duration=duration if phase == "over" else cut)
    if phase == "over":
        winner = {"p1": "P1 승리", "p2": "P2 승리", "draw": "무승부"}[result["winner"]]
        st.markdown(f"# {winner}", text_alignment="center")
    scoreboard(result)

# run_every fragment는 **반드시 맨 마지막**에 호출한다.
# 입력 패널보다 먼저 호출하면 0.5초 주기 재실행이 초기 렌더링을 선점해
# 입력창까지 도달하지 못한다 (2세션 동시 접속에서 재현됨).
watcher()

"""core.py 로직 테스트 — streamlit 없이 돌아야 한다. 실행: python -m pytest -q"""

import math
from pathlib import Path

import pandas as pd
import pytest

import core

CSV = Path(__file__).parent / "data" / "high_diamond_ranked_10min.csv"


@pytest.fixture(scope="module")
def engine():
    return core.fit_engine(pd.read_csv(CSV))


def spam(cmd, k, start=0.0, gap=None):
    """같은 명령을 k번, 처리시간보다 조금 빠르게 친다."""
    gap = gap if gap is not None else core.SEC + 0.05
    return [(cmd, start + i * gap) for i in range(k)]


# ---------------------------------------------------------------- 엔진
def test_engine_learns_from_data(engine):
    assert engine.auc > 0.78
    assert engine.coef["goldDiff"] > 0
    assert engine.coef["dragDiff"] > 0
    assert engine.coef["towerDiff"] < 0          # 대리변수 역전
    assert engine.coef["killDiff"] < 0
    assert len(engine.coef) == 11


def test_caps_and_cooldowns_come_from_data(engine):
    assert 5000 < engine.axis_cap["goldDiff"] < 7500
    assert engine.unit_cap["dragon"] == 1
    # 쿨타임 = (600 / 10분평균) / 10
    assert math.isclose(engine.cooldown["kill"], 9.70, abs_tol=0.1)
    assert math.isclose(engine.cooldown["ward"], 2.69, abs_tol=0.1)
    assert math.isclose(engine.cooldown["wardkill"], 21.24, abs_tol=0.2)
    # 60초를 넘는 쿨타임은 0으로 두고 캡·스폰이 대신 막는다
    assert engine.cooldown.get("tower", 0.0) == 0.0


def test_spawn_times_are_compressed_ten_to_one(engine):
    assert engine.spawn["dragon"] == 30.0        # 5:00
    assert engine.spawn["herald"] == 48.0        # 8:00


def test_every_command_has_a_real_cap(engine):
    """롤의 타워 개수·레벨 상한처럼 모든 명령에 상한이 있어야 한다.
    무한히 칠 수 있는 명령이 하나라도 있으면 그것만 치는 게 답이 된다."""
    for cmd, spec in core.COMMANDS.items():
        cap = engine.unit_cap[cmd]
        cd = engine.cooldown.get(cmd, 0.0)
        usable = core.DURATION - engine.spawn.get(cmd, 0.0)
        by_cd = int(usable / cd) + 1 if cd else 10**9
        by_time = int(usable / (spec["n"] * spec["sec"]))
        assert min(cap, by_cd, by_time) < 10**9, f"{cmd}에 상한이 없다"
        assert cap < 1000, f"{cmd} 단위캡이 사실상 무한이다: {cap}"


def test_gold_cap_comes_from_the_axis_cap(engine):
    """gold는 피처가 아니라 자원 축이므로 축 캡에서 횟수 상한을 끌어온다."""
    assert engine.unit_cap["gold"] == int(engine.axis_cap["goldDiff"] / engine.reward["gold"][0])
    assert 50 < engine.unit_cap["gold"] < 90


def test_level_cap_matches_real_lol_levels(engine):
    """롤 최대 레벨은 18이지만 그건 20~25분대다.
    이 데이터는 10분 스냅샷이고 평균 6.92 / 최대 8.0레벨이다.
    레벨 1에서 시작하므로 10분에 오르는 건 최대 7레벨 → 캡 7회."""
    df = pd.read_csv(CSV)
    expected = int(round(float(df["blueAvgLevel"].max()) - 1.0))
    assert engine.unit_cap["level"] == expected == 7
    assert 5 <= engine.unit_cap["level"] <= 10, "실제 레벨 범위 안이어야 한다"
    # 캡까지 치면 경험치 축 캡에 정확히 닿는다
    _, exp_each = engine.reward["level"]
    assert abs(exp_each * engine.unit_cap["level"] - engine.axis_cap["expDiff"]) < 1.0


def test_level_diff_stays_inside_the_data(engine):
    """레벨 캡을 전부 써도 데이터가 본 레벨차 범위를 넘지 않아야 한다."""
    _, exp_each = engine.reward["level"]
    EXP_PER_LEVEL = 3689.0        # 데이터 회귀: 경험치차 = 3689 × 레벨차
    max_level_diff = exp_each * engine.unit_cap["level"] / EXP_PER_LEVEL
    assert max_level_diff < 2.6, f"관측 최대 레벨차 2.6을 넘는다: {max_level_diff:.2f}"


def test_level_cap_is_enforced(engine):
    """레벨 상한을 넘겨 치면 거부된다 (조용히 무시하지 않는다)."""
    cap = engine.unit_cap["level"]
    side, _, _ = core.simulate(spam("level", cap + 15), [], engine)
    assert side.done.get("level", 0) == cap
    assert any(w == core.R_CAP for _c, w, _t in side.rejected)


def test_tower_cap_matches_observed_maximum(engine):
    """롤 전체 타워는 11개지만 10분 데이터 관측 최대는 4다."""
    assert engine.unit_cap["tower"] == 4


def test_dragon_and_herald_are_not_interchangeable(engine):
    """둘을 묶으면 안 된다 — 드래곤 계수가 전령의 3배 이상이다."""
    assert engine.coef["dragDiff"] > 3 * engine.coef["heraldDiff"] > 0
    n_d, n_h = core.COMMANDS["dragon"]["n"], core.COMMANDS["herald"]["n"]
    d = core.battle(spam("dragon", n_d, start=31.0), [], engine)["p1"]["score"]
    h = core.battle(spam("herald", n_h, start=49.0), [], engine)["p1"]["score"]
    assert d > h + 5, f"드래곤({d})이 전령({h})보다 확실히 높아야 한다"


# ---------------------------------------------------------------- 형식
def test_empty_queue_is_a_draw(engine):
    r = core.battle([], [], engine)
    assert r["winner"] == "draw"
    assert r["p1"]["score"] == 50
    assert isinstance(r["p1"]["reasons"], list) and r["p1"]["reasons"]


def test_return_format_is_fixed(engine):
    r = core.battle([("gold", 0.0)], [], engine)["p1"]
    assert set(r) == {"score", "level", "reasons"}
    assert isinstance(r["score"], int) and 0 <= r["score"] <= 100
    assert isinstance(r["level"], str)
    assert all(isinstance(x, str) for x in r["reasons"])


def test_scores_always_sum_to_100(engine):
    for p1, p2 in [(spam("tower", 4), []),
                   (spam("gold", 8), spam("level", 5)),
                   (spam("dragon", 4, 31), spam("kill", 4))]:
        r = core.battle(p1, p2, engine)
        assert r["p1"]["score"] + r["p2"]["score"] == 100


# ---------------------------------------------------------------- N타 분할
def test_tower_is_negative_until_the_fifth_press(engine):
    scores = [core.battle(spam("tower", k), [], engine)["p1"]["score"] for k in range(1, 6)]
    assert scores[0] < 50, scores
    assert scores[3] < scores[0], scores
    assert scores[4] > 50, scores
    assert scores[4] - scores[3] > 10, scores


def test_n_split_preserves_the_data_total(engine):
    for cmd in ("tower", "cs"):
        n = core.COMMANDS[cmd]["n"]
        a, _, _ = core.simulate(spam(cmd, n), [], engine)
        terms = core._terms(engine, a, core.Side())
        assert math.isclose(sum(terms.values()), engine.net_logit(cmd), abs_tol=1e-9), cmd


def test_incomplete_tower_is_pure_loss(engine):
    r = core.battle(spam("tower", 5, start=core.DURATION - 1.0), [], engine)
    assert r["p1"]["score"] < 50


# ---------------------------------------------------------------- 쿨타임
def test_cooldown_blocks_repeat(engine):
    """kill 쿨타임 9.7초 — 연속으로 두 번 완성할 수 없다."""
    n = core.COMMANDS["kill"]["n"]
    side, _, _ = core.simulate(spam("kill", n * 2), [], engine)
    assert side.done.get("kill", 0) == 1
    assert any(w == core.R_COOLDOWN for _c, w, _t in side.rejected)


def test_cooldown_expires(engine):
    """쿨타임이 지나면 다시 칠 수 있다."""
    n = core.COMMANDS["kill"]["n"]
    presses = spam("kill", n) + spam("kill", n, start=engine.cooldown["kill"] + 3.0)
    side, _, _ = core.simulate(presses, [], engine)
    assert side.done.get("kill", 0) == 2


def test_spawn_gate_blocks_early_objective(engine):
    """드래곤은 30초(5:00) 전에는 칠 수 없다."""
    n = core.COMMANDS["dragon"]["n"]
    early, _, _ = core.simulate(spam("dragon", n, start=0.0), [], engine)
    assert early.done.get("dragon", 0) == 0
    assert any(w == core.R_SPAWN for _c, w, _t in early.rejected)
    late, _, _ = core.simulate(spam("dragon", n, start=31.0), [], engine)
    assert late.done.get("dragon", 0) == 1


def test_herald_spawns_at_48s(engine):
    n = core.COMMANDS["herald"]["n"]
    a, _, _ = core.simulate(spam("herald", n, start=40.0), [], engine)
    assert a.done.get("herald", 0) == 0
    b, _, _ = core.simulate(spam("herald", n, start=48.5), [], engine)
    assert b.done.get("herald", 0) == 1


# ---------------------------------------------------------------- 와드 상호작용
def test_ward_blocks_the_snipe(engine):
    """시야가 있으면 기습당하지 않는다 — wardkill은 와드만 걷어낸다."""
    me, foe, _ = core.simulate([("wardkill", 5.0)], [("ward", 0.0)], engine)
    assert me.swept, "와드를 걷어낸 기록이 남아야 한다"
    assert not foe.sniped, "시야가 있었으므로 기습은 실패한다"
    assert foe.frozen_until == 0.0
    assert foe.live_wards(6.0) == 0, "와드는 사라진다"


def test_snipe_lands_on_a_blind_enemy(engine):
    """와드가 없으면 바로 기습당한다."""
    me, foe, _ = core.simulate([("wardkill", 5.0)], [("gold", 0.0)], engine)
    assert me.done.get("wardkill", 0) == 1
    assert foe.sniped and foe.frozen_until > 5.0
    assert not me.swept


def test_two_wardkills_needed_against_a_warded_enemy(engine):
    """와드를 벗긴 뒤에야 기습이 들어간다 — 기습 비용이 2배가 된다."""
    cd = engine.cooldown["wardkill"]
    me, foe, _ = core.simulate(
        [("wardkill", 5.0), ("wardkill", 5.0 + cd + 1.0)], [("ward", 0.0)], engine)
    assert len(me.swept) == 1 and len(foe.sniped) == 1


def test_ward_cooldown_limits_supply(engine):
    """와드 쿨타임 2.69초 — 60초에 최대 23개 정도다."""
    side, _, _ = core.simulate(spam("ward", 60, gap=0.4), [], engine)
    expected = int(core.DURATION / engine.cooldown["ward"]) + 1
    assert side.done.get("ward", 0) <= expected


# ---------------------------------------------------------------- 선점·캡
def test_contested_objective_goes_to_the_faster_side(engine):
    n = core.COMMANDS["dragon"]["n"]
    r = core.battle(spam("dragon", n, start=30.1), spam("dragon", n, start=34.0), engine)
    assert r["side1"].counts.get("dragDiff", 0) == 1
    assert r["side2"].counts.get("dragDiff", 0) == 0
    assert r["winner"] == "p1"


def test_firstblood_is_only_won_once(engine):
    r = core.battle([("firstblood", 0.0)], [("firstblood", 1.0)], engine)
    total = r["side1"].counts.get("firstBlood", 0) + r["side2"].counts.get("firstBlood", 0)
    assert total == 1


# ---------------------------------------------------------------- 기타
def test_overflow_presses_are_dropped(engine):
    side, _, _ = core.simulate([("gold", core.DURATION - 0.05)], [], engine)
    assert side.done.get("gold", 0) == 0
    assert any(w == core.R_TIME for _c, w, _t in side.rejected)


def test_rate_limit_rejects_measured_loss_zone():
    kept, rejected = core.rate_limit([("gold", i * 0.05) for i in range(10)])
    assert len(kept) < 10 and rejected
    kept2, rejected2 = core.rate_limit([("gold", i * 0.3) for i in range(10)])
    assert len(kept2) == 10 and not rejected2


def test_ward_is_an_honest_trap(engine):
    assert abs(engine.net_logit("ward")) < 0.01
    assert abs(engine.net_logit("wardkill")) < 0.01
    assert core.battle(spam("ward", 60, gap=0.4), [], engine)["p1"]["score"] <= 55


def test_available_reports_why(engine):
    me = core.Side()
    ok, why = core.available(engine, me, "dragon", 10.0, core.new_hp())
    assert not ok and why == core.R_SPAWN
    ok, _ = core.available(engine, me, "gold", 10.0, core.new_hp())
    assert ok


def test_suggest_sequence_is_mixed_and_fits(engine):
    seq = core.suggest_sequence(engine)
    assert seq
    assert len(set(seq)) >= 3, f"전략이 단일 명령으로 붕괴했다: {set(seq)}"


def test_symmetry(engine):
    p = spam("gold", 10)
    r = core.battle(p, list(p), engine)
    assert r["p1"]["score"] == r["p2"]["score"] == 50
    assert r["winner"] == "draw"


def test_firstblood_also_grants_a_kill(engine):
    """퍼블은 정의상 킬이다 — 데이터에서 퍼블 획득 & 킬 0개인 경기는 0건이다."""
    side, _, _ = core.simulate([("firstblood", 0.5)], [], engine)
    assert side.counts.get("firstBlood", 0) == 1
    assert side.counts.get("killDiff", 0) == 1, "킬도 같이 들어와야 한다"
    assert side.done.get("kill", 0) == 1
    # 킬 쿨타임도 같이 돌아야 한다
    assert side.remaining_cd("kill", 1.0) > 0


def test_firstblood_swing_matches_kill_plus_bonus(engine):
    """퍼블 스윙 = 킬 1개 + 퍼블 보너스. 보너스만 주던 때(약 2%p)보다 훨씬 커야 한다."""
    r = core.battle([("firstblood", 0.5)], [], engine)
    gap = r["p1"]["score"] - r["p2"]["score"]
    assert 10 <= gap <= 20, f"퍼블 격차가 {gap}%p — 킬+보너스(약 14%p) 범위여야 한다"


def test_firstblood_kill_respects_cap(engine):
    """퍼블로 받은 킬도 킬 캡에 포함된다."""
    n = core.COMMANDS["kill"]["n"]
    presses = [("kill", i * 0.35) for i in range(n)] + [("firstblood", 20.0)]
    side, _, _ = core.simulate(presses, [], engine)
    assert side.done.get("kill", 0) == 2        # 직접 1 + 퍼블로 1


# ---------------------------------------------------------------- 오브젝트 스틸
def test_objective_has_shared_hp(engine):
    """드래곤 체력은 공유다 — 양쪽 타격이 같은 체력을 깎는다."""
    n = core.COMMANDS["dragon"]["n"]          # 4
    # P1이 2대, P2가 2대 → 4대째(P2)가 막타
    p1 = [("dragon", 31.0), ("dragon", 31.7)]
    p2 = [("dragon", 31.35), ("dragon", 32.1)]
    a, b, hp = core.simulate(p1, p2, engine)
    assert hp["dragon"] == 0, "4대 맞았으면 죽어야 한다"
    assert a.hits["dragon"] == 2 and b.hits["dragon"] == 2
    got = a.counts.get("dragDiff", 0) + b.counts.get("dragDiff", 0)
    assert got == 1, "한 쪽만 가져간다"
    assert n == 4


def test_last_hit_steals_the_objective(engine):
    """3대 때려도 막타를 뺏기면 아무것도 못 받는다 (실제 롤의 스틸)."""
    p1 = [("dragon", 31.0), ("dragon", 31.5), ("dragon", 32.0)]   # 3대
    p2 = [("dragon", 32.6)]                                        # 막타만
    a, b, hp = core.simulate(p1, p2, engine)
    assert hp["dragon"] == 0
    assert a.hits["dragon"] == 3 and b.hits["dragon"] == 1
    assert a.counts.get("dragDiff", 0) == 0, "3대 때린 쪽은 못 가져간다"
    assert b.counts.get("dragDiff", 0) == 1, "막타 친 쪽이 가져간다"
    assert "dragon" in a.stolen, "스틸당한 기록이 남아야 한다"
    r = core.battle(p1, p2, engine)
    assert r["winner"] == "p2"


def test_hits_before_the_kill_are_wasted(engine):
    """막타를 못 치면 투자한 타수는 그냥 버려진다 — 승률에 아무 영향 없다."""
    waster = core.battle([("dragon", 31.0), ("dragon", 31.5)], [], engine)
    assert waster["p1"]["score"] == 50, "체력만 깎고 못 먹으면 이득이 없다"


def test_objective_is_gone_after_the_last_hit(engine):
    """막타 이후 추가 타격은 거부된다."""
    n = core.COMMANDS["dragon"]["n"]
    side, _, hp = core.simulate(spam("dragon", n + 4, start=31.0), [], engine)
    assert hp["dragon"] == 0
    assert side.done.get("dragon", 0) == 1
    assert any(w == core.R_CAP for _c, w, _t in side.rejected)


def test_herald_shared_hp_is_two(engine):
    a, b, hp = core.simulate([("herald", 49.0)], [("herald", 49.5)], engine)
    assert hp["herald"] == 0
    assert b.counts.get("heraldDiff", 0) == 1 and a.counts.get("heraldDiff", 0) == 0
    assert "herald" in a.stolen


# ---------------------------------------------------------------- 유틸리티 (ward / wardkill)
def test_ward_expires(engine):
    """와드는 WARD_DURATION 뒤 사라진다."""
    side, _, _ = core.simulate([("ward", 1.0)], [], engine)
    assert side.live_wards(2.0) == 1
    assert side.live_wards(1.0 + core.WARD_DURATION + 1.0) == 0


def test_ward_gives_vision(engine):
    """와드가 살아 있는 동안 상대 큐가 보인다."""
    side, _, _ = core.simulate([("ward", 1.0)], [], engine)
    assert side.has_vision(3.0)
    assert not side.has_vision(1.0 + core.WARD_DURATION + 1.0)
    assert not core.Side().has_vision(3.0)


def test_wardkill_freezes_the_enemy(engine):
    """기습 — 시야 없는 상대를 FREEZE초간 입력 불가로 만든다 (사망 리스폰)."""
    foe = [("gold", 5.0 + i * 0.4) for i in range(12)]
    a, b, _ = core.simulate([("wardkill", 5.0)], foe, engine)
    assert a.done.get("wardkill", 0) == 1
    assert b.sniped, "기습 기록이 남아야 한다"
    assert b.frozen_until > 5.0
    assert any(w == core.R_FROZEN for _c, w, _t in b.rejected), "정지 중 입력은 거부된다"
    _, clean, _ = core.simulate([], foe, engine)
    assert b.gold < clean.gold, "정지당한 만큼 골드가 줄어든다"


def test_freeze_is_temporary_not_destructive(engine):
    """정지가 풀리면 전략을 그대로 이어간다 — 잃는 건 템포뿐이다."""
    foe = [("gold", 20.0 + i * 0.4) for i in range(10)]
    _, b, _ = core.simulate([("wardkill", 5.0)], foe, engine)
    assert b.done.get("gold", 0) == 10, "정지가 끝난 뒤 입력은 전부 정상 처리된다"


def test_wardkill_cooldown_limits_snipes(engine):
    """기습 쿨타임 21.24초 — 60초에 3회가 한계다."""
    cd = engine.cooldown["wardkill"]
    me, foe, _ = core.simulate(spam("wardkill", 40, gap=1.0), [("gold", 1.0)], engine)
    assert me.done.get("wardkill", 0) <= int(core.DURATION / cd) + 1


def test_utility_cannot_bypass_the_model(engine):
    """유틸리티는 상대 입력을 깎을 뿐, 승률을 직접 건드리지 않는다.
    상대가 아무것도 안 치면 기습해도 점수가 안 변한다."""
    r = core.battle([("ward", 0.0), ("wardkill", 30.0)], [], engine)
    assert r["p1"]["score"] <= 51, "와드·기습 자체로는 승률이 거의 안 오른다"
    # 상대가 아무것도 안 치면 정지시켜도 뺏을 게 없다
    assert r["p2"]["score"] >= 49


# ---------------------------------------------------------------- 모델 검증
def test_mirror_augmentation_makes_the_model_symmetric(engine):
    """블루/레드 라벨은 임의다 — 미러 증강으로 절편이 정확히 0이 되어야 한다."""
    assert abs(engine.intercept) < 1e-6, f"절편이 0이 아니다: {engine.intercept}"


def test_probabilities_sum_to_exactly_100(engine):
    """미러 증강 덕분에 P(나)+P(상대)가 반올림 없이도 정확히 1이다."""
    import math
    mine = core.Side(gold=2500.0, exp=1800.0, counts={"dragDiff": 1, "towerDiff": 2})
    theirs = core.Side(gold=400.0, exp=300.0, counts={"killDiff": 3})
    t1 = sum(core._terms(engine, mine, theirs).values())
    t2 = sum(core._terms(engine, theirs, mine).values())
    assert math.isclose(t1, -t2, abs_tol=1e-9), "기여도가 정확히 반대여야 한다"
    r = core.battle([], [], engine)
    assert r["p1"]["score"] + r["p2"]["score"] == 100


def test_tower_support_covers_the_game_range(engine):
    """게임은 양쪽 ±4 타워를 허용한다 — 학습 분포가 이를 포함해야 한다."""
    assert engine.unit_cap["tower"] == 4


def test_model_beats_the_gold_only_baseline(engine):
    """11피처 모델이 골드차 단독보다 나아야 한다 (안 그러면 복잡도가 낭비다)."""
    assert engine.auc > 0.805


def test_room_phases_from_files_only(tmp_path):
    """두 기기가 파일만 보고 같은 방 상태를 얻는다 — 지난 경기의 수락은 섞이지 않는다."""
    import json, time
    assert core.read_state(tmp_path)["phase"] == "idle"
    core.invite(tmp_path)
    inv = core.read_state(tmp_path)["invite"]
    # 지난 invite에 대한 P2 수락이 남아 있어도 한쪽만 수락한 상태다
    (tmp_path / "accept_P2.json").write_text(json.dumps({"invite": inv - 1, "at": time.time()}))
    core.accept(tmp_path, "P1", inv)
    assert core.read_state(tmp_path)["phase"] == "lobby"
    core.accept(tmp_path, "P2", inv)
    assert core.read_state(tmp_path)["phase"] == "countdown"

    def accepted_ago(sec):
        for slot in core.SLOTS:
            (tmp_path / f"accept_{slot}.json").write_text(json.dumps({"invite": inv, "at": time.time() - sec}))
        return core.read_state(tmp_path)["phase"]
    assert accepted_ago(10) == "playing"
    assert accepted_ago(core.COUNTDOWN + core.DURATION + 1) == "over"

    core.append_press(tmp_path, "P1", "gold", 1.0)
    core.append_press(tmp_path, "P1", "tower", 5.0)
    with (tmp_path / "p1.jsonl").open("a") as f:
        f.write('{"cmd": "kill"')                       # 반쯤 쓰인 줄
    assert core.read_presses(tmp_path, "P1") == [("gold", 1.0), ("tower", 5.0)]
    assert core.read_presses(tmp_path, "P1", until=2.0) == [("gold", 1.0)]
    core.invite(tmp_path)                                # 새 신청은 이전 입력·수락을 지운다
    assert core.read_presses(tmp_path, "P1") == [] and core.read_state(tmp_path)["phase"] == "lobby"

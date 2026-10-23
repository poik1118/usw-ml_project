"""큐 + 쿨타임 기반 승률 줄다리기 — 로직 전부. streamlit을 import하지 않는다.

설계 원칙
---------
값(계수·골드·경험·캡·쿨타임)은 **전부 데이터에서 유도**한다. 하드코딩하지 않는다.
설계 변수는 `SEC`(타당 처리시간)와 명령어별 `n`(몇 타에 완성) 둘뿐이다.

시간 압축은 **10:1** 이다 — 데이터는 10분(600초) 경기, 게임은 60초다.
그래서 쿨타임 = (데이터 평균 빈도로 본 실제 간격) ÷ 10 으로 바로 환산된다.

3단계(11~13주)에서 win_rate 호출을 requests.post로 바꾼다. 화면 코드는 그대로 둔다.
"""

from __future__ import annotations

import heapq
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

FEATURES = [
    "goldDiff", "expDiff", "killDiff", "csDiff", "jungleDiff", "dragDiff",
    "heraldDiff", "towerDiff", "wardDiff", "wardKillDiff", "firstBlood",
]
AXIS = ("goldDiff", "expDiff")

DURATION = 60.0        # 게임 길이(초). 실제 10분을 10:1로 압축한 것.
COMPRESS = 10.0        # 시간 압축비. 쿨타임·스폰 시각 환산에 쓴다.
MIN_GAP = 0.25         # 입력 최소 간격(초). 측정값: 0.20초 미만이면 서버에서 유실된다.
SEC = 0.3              # 타당 처리시간. 측정된 서버 하한(0.25초) 바로 위 — 즉각 반영된다.
QUEUE_CAP = 4          # 큐 대기 상한(처리 중 포함)

# 오브젝트 스폰 시각(실제 분) — 롤 도메인 지식이고, 데이터 획득률로 교차검증했다.
#   드래곤 5:00 → 창 5분, 양팀 획득률 77.5% (분당 15.5%)
#   전령  8:00 → 창 2분, 양팀 획득률 34.8% (분당 17.4%)  ← 드래곤과 정합
#   전령 9:50 가정은 10초 창에 34.8%라 물리적으로 불가능하다 → 8:00이 데이터와 맞는다.
SPAWN_MIN = {"dragon": 5.0, "herald": 8.0}

# 드래곤·전령·정글캠프를 하나로 묶지 않는 이유 (측정값):
#   분리(dragDiff+heraldDiff) AUC 0.81055  vs  통합(eliteDiff) 0.80984   → 분리가 낫다
#   raw 계수: 드래곤 +0.3156 / 전령 +0.0696                              → 4.5배 차이
#   골드 통제 후 실측 승률 격차: 드래곤 +13.0%p / 전령 +4.2%p             → 3.1배 차이
#   정글캠프는 레인 CS와 상관 0.067로 별개 자원이지만 계수가 불안정하다
#     (부트스트랩 양수비율 37.5%) → 게임에선 '효과가 애매한 함정'으로 둔다.
# 묶으면 드래곤을 과소평가하고 전령을 과대평가한다. 셋 다 따로 간다.

LEVELS = ((70, "유리"), (55, "약간 유리"), (45, "박빙"), (30, "약간 불리"))

COMMANDS: dict[str, dict] = {
    # 명령어        피처                      n  contested
    "gold":       dict(feature=None,           n=1, contested=False),
    # 레벨업은 경험치를 모아야 한다 → 3타. 캡을 20회에서 데이터 기반 7회로 줄이면서
    # 1회 가치가 3배로 커졌으므로(효율 0.648/s), n으로 보정해 기존 균형을 유지한다.
    "level":      dict(feature=None,           n=3, contested=False),
    "cs":         dict(feature="csDiff",       n=1, contested=False),
    "jungle":     dict(feature="jungleDiff",   n=1, contested=False),
    "kill":       dict(feature="killDiff",     n=4, contested=False),
    "tower":      dict(feature="towerDiff",    n=5, contested=False),
    "dragon":     dict(feature="dragDiff",     n=4, contested=True),
    "herald":     dict(feature="heraldDiff",   n=2, contested=True),
    "ward":       dict(feature="wardDiff",     n=1, contested=False),
    "wardkill":   dict(feature="wardKillDiff", n=1, contested=False),
    # 퍼블은 **정의상 킬이다** (데이터: 퍼블 획득 4,987경기 중 킬 0개는 0건).
    # 1단계 회귀가 killDiff를 통제하고 뽑은 +86.6골드는 '킬을 뺀 퍼블 보너스만'이고,
    # 이는 실제 롤의 퍼블 보너스(400−300=+100골드)와 거의 일치한다.
    # 따라서 완성 시 킬 1개까지 같이 줘야 데이터와 맞는다 → also="kill".
    "firstblood": dict(feature="firstBlood",   n=1, contested=True, also="kill"),
}
for _s in COMMANDS.values():
    _s["sec"] = SEC

# 데이터 열 → 쿨타임을 계산할 명령어
_FREQ_COL = {
    "cs": "blueTotalMinionsKilled", "jungle": "blueTotalJungleMinionsKilled",
    "ward": "blueWardsPlaced", "wardkill": "blueWardsDestroyed", "kill": "blueKills",
}
# 와드/기습 상호작용 — 실제 롤의 "시야가 있으면 갱킹당하지 않는다"를 그대로 옮겼다.
#   상대에게 살아 있는 와드가 있으면 → wardkill은 **와드 1개만 걷어낸다** (기습 실패)
#   상대에게 와드가 없으면        → wardkill은 **기습 성공**, 상대를 FREEZE초 정지시킨다
# 그래서 와드는 '기습 방어'가 되고, 기습하려면 먼저 와드를 벗겨야 한다.
DISRUPTOR = "wardkill"

# ─── 유틸리티 효과 ───────────────────────────────────────────────────────
# ward·wardkill은 데이터상 순 logit이 0.00064·0.00702로 **사실상 0**이다
# (60초 몰빵해도 0.015·0.021 — gold의 2.868 대비 100배 이상 약하다).
# 데이터가 "와드는 승률에 직접 기여하지 않는다"고 말하는 건 맞지만, 실제 롤에서
# 와드의 가치는 **시야 정보**이지 직접 전투력이 아니다. 데이터에 그 정보 가치를
# 담을 열이 없으므로, 여기서만 게임 메커니즘으로 보완한다.
#
# ★ 이 둘은 이 프로젝트에서 **데이터로 유도하지 않은 유일한 수치**다. 발표에서 그렇게 밝힌다.
#
# 설계 원칙: 유틸리티는 **모델을 우회하지 않는다.** 상대의 입력을 깎아
#            상대의 골드·경험·오브젝트를 줄이고, 그 결과가 모델을 통해 승률이 된다.
WARD_DURATION = 10.0   # 와드 지속(초). 실제 롤 설치형 와드 ~100초 ÷ 압축비 10
#
# wardkill = 시야를 지우고 **기습**한다. 상대 와드 1개를 제거하고 상대를 FREEZE초간
# 입력 불가로 만든다. '큐 취소'는 측정해 보니 불가능했다 — SEC=0.3초라 처리가 타이핑보다
# 빨라서 큐가 거의 비어 있다(기습 1회당 평균 0.9개밖에 못 끊었고, 섞으면 −5.6점 손해).
# 그래서 큐가 아니라 **시간**을 뺏는다. 실제 롤 10분 시점 사망 리스폰 타이머는
# 레벨에 따라 약 20~35초다. ÷ 압축비 10 = 2.0~3.5초이고, 측정 결과 하한(2.5초)에서는
# 섞을 가치가 없어서(평균 +0.0점) **상한 3.5초**를 택했다 (평균 +0.4점).
FREEZE = 3.5           # 기습당한 쪽이 입력하지 못하는 시간(초)
R_FROZEN = "기습당해 정지"

# gold/level은 데이터 피처가 아니라 '자원 축'이다. 보상·캡을 fit_engine이 데이터에서 뽑는다.
#   gold  : 1회 = 100골드 (고정). 캡은 골드차 축 캡 ÷ 100
#   level : 1회 = (경험치 축 캡 ÷ LEVEL_CAP). 캡은 **데이터의 실제 레벨 상승폭**
#
# 롤 최대 레벨은 18이지만 그건 20~25분대 이야기다. 이 데이터는 10분 스냅샷이고
# 평균 레벨 6.92 / 최대 8.0 (5레벨 7경기 · 6레벨 813 · 7레벨 8,855 · 8레벨 204)이다.
# 레벨 1에서 시작하므로 10분에 오르는 건 최대 **7레벨** → level 명령 캡 7회.
DIRECT = {"gold": ("gold", 100.0), "level": ("exp", None)}   # level 보상은 데이터에서 계산
LEVEL_COL = "blueAvgLevel"
LEVEL_START = 1.0      # 롤은 1레벨에서 시작한다

# 거부 사유
R_COOLDOWN, R_SPAWN, R_QUEUE, R_CAP, R_TIME = (
    "쿨타임", "미스폰", "큐가득", "캡/선점", "시간초과")


@dataclass
class Engine:
    coef: dict[str, float]
    intercept: float
    reward: dict[str, tuple[float, float]]
    unit_cap: dict[str, int]
    axis_cap: dict[str, float]
    cooldown: dict[str, float]          # 명령어 → 쿨타임(초). 없으면 0
    spawn: dict[str, float]             # 명령어 → 최초 사용 가능 시각(초)
    auc: float = 0.0

    def net_logit(self, cmd: str) -> float:
        spec = COMMANDS[cmd]
        own = self.coef.get(spec["feature"], 0.0) if spec["feature"] else 0.0
        g, e = self.reward[cmd]
        return own + self.coef["goldDiff"] * g + self.coef["expDiff"] * e

    def efficiency(self, cmd: str) -> float:
        """초당 logit. 쿨타임이 있으면 '쿨타임당'이 실질 효율이다."""
        spec = COMMANDS[cmd]
        cost = max(spec["n"] * spec["sec"], self.cooldown.get(cmd, 0.0))
        return self.net_logit(cmd) / cost if cost else 0.0


def features(df):
    """원본 40열 → 모델 피처 11개 (Blue − Red 차이). 학습·화면·실험이 전부 이 정의 하나를 쓴다."""
    import pandas as pd

    return pd.DataFrame({
        "goldDiff": df["blueGoldDiff"],
        "expDiff": df["blueExperienceDiff"],
        "killDiff": df["blueKills"] - df["blueDeaths"],
        "csDiff": df["blueTotalMinionsKilled"] - df["redTotalMinionsKilled"],
        "jungleDiff": df["blueTotalJungleMinionsKilled"] - df["redTotalJungleMinionsKilled"],
        "dragDiff": df["blueDragons"] - df["redDragons"],
        "heraldDiff": df["blueHeralds"] - df["redHeralds"],
        "towerDiff": df["blueTowersDestroyed"] - df["redTowersDestroyed"],
        "wardDiff": df["blueWardsPlaced"] - df["redWardsPlaced"],
        "wardKillDiff": df["blueWardsDestroyed"] - df["redWardsDestroyed"],
        "firstBlood": df["blueFirstBlood"] * 2 - 1,
    })[FEATURES]


def fit_engine(df) -> Engine:
    """원본 데이터로 엔진을 학습한다. 계수·보상·캡·쿨타임을 전부 데이터에서 뽑는다."""
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    d = features(df)
    y = df["blueWins"]

    X = d.to_numpy(dtype=float)
    yv = y.to_numpy()

    # 미러 증강 — 블루/레드 라벨은 임의다. 모든 차이값의 부호를 뒤집고 정답도 뒤집은
    # 사본을 더한다. 공짜로 세 가지가 해결된다 (검증 완료, AUC는 0.8109로 동일):
    #   1) 절편이 정확히 0이 된다 → 1대1에서 절편을 빼는 게 꼼수가 아니라 유도 결과가 된다
    #   2) P(나) + P(상대) = 100%가 **정확히** 성립한다 (증강 전 평균 오차 0.42%p)
    #   3) towerDiff 관측 범위가 -2~+4(샘플링 노이즈)에서 ±4로 대칭이 되어
    #      게임이 만드는 상태의 13.9%가 분포 밖이던 문제가 사라진다
    Xa = np.vstack([X, -X])
    ya = np.concatenate([yv, 1 - yv])

    # 피처 범위가 ±11,000(골드)부터 ±1(드래곤)까지라 원단위 학습은 수렴이 매우 느리다.
    # 표준화 학습 후 계수를 원단위로 역변환한다 — raw 계수는 수학적으로 동일하다.
    mu, sd = Xa.mean(axis=0), Xa.std(axis=0)
    lg = LogisticRegression(max_iter=3000).fit((Xa - mu) / sd, ya)
    coef = dict(zip(FEATURES, (float(v) for v in lg.coef_[0] / sd)))
    intercept = float(lg.intercept_[0] - (lg.coef_[0] * mu / sd).sum())
    auc = float(cross_val_score(
        make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        d, y, cv=5, scoring="roc_auc").mean())      # 평가는 원본으로만 한다

    # 캡 = 데이터 관측 범위. 임의 조정이 아니라 모델의 정의역이다.
    axis_cap = {a: float(np.percentile(np.abs(Xa[:, FEATURES.index(a)]), 99)) for a in AXIS}

    # 1단계 회귀: 행동 1단위가 실제로 골드·경험을 얼마 주는가
    acts = ["killDiff", "csDiff", "jungleDiff", "towerDiff", "wardDiff",
            "wardKillDiff", "firstBlood"]
    A = d[acts]
    g_coef = dict(zip(acts, LinearRegression().fit(A, d["goldDiff"]).coef_))
    e_coef = dict(zip(acts, LinearRegression().fit(A, d["expDiff"]).coef_))

    # 레벨 캡 = 데이터에서 10분에 실제로 오르는 레벨 수 (최대 평균레벨 − 시작 레벨 1)
    level_cap = int(round(float(df[LEVEL_COL].max()) - LEVEL_START))      # 8.0 − 1 = 7

    reward: dict[str, tuple[float, float]] = {}
    for cmd, spec in COMMANDS.items():
        if cmd in DIRECT:
            kind, amount = DIRECT[cmd]
            if kind == "exp":
                # level 1회 = 경험치 축 캡을 레벨 수로 나눈 값 → 캡까지 치면 축 캡에 정확히 닿는다
                amount = axis_cap["expDiff"] / level_cap
            reward[cmd] = (amount, 0.0) if kind == "gold" else (0.0, amount)
        else:
            f = spec["feature"]
            # 드래곤·전령은 골드·경험을 주지 않는다 — 효과가 자기 계수뿐인 '골드 밖' 변수다.
            reward[cmd] = (float(g_coef[f]), float(e_coef[f])) if f in g_coef else (0.0, 0.0)

    unit_cap: dict[str, int] = {}
    for cmd, spec in COMMANDS.items():
        f = spec["feature"]
        if f is None:
            # gold/level도 명시적으로 센다. 축 캡에 닿으면 한계이득이 0이 되는데,
            # 그걸 조용히 무시하면 화면에 "왜 안 오르지?"가 된다. 아예 못 치게 막는다.
            kind, _ = DIRECT[cmd]
            unit_cap[cmd] = (int(axis_cap["goldDiff"] / reward[cmd][0]) if kind == "gold"
                             else level_cap)
        else:
            # 미러 증강된 Xa를 쓴다 — 관측 범위가 대칭이라 비대칭 샘플링 노이즈가 없다.
            col = Xa[:, FEATURES.index(f)]
            unit_cap[cmd] = int(max(abs(col.min()), abs(col.max())))

    # 쿨타임 = (실제 1회당 간격) ÷ 압축비. 데이터 평균 빈도에서 바로 나온다.
    # 60초를 넘는 것(tower·dragon·herald·firstblood)은 쿨타임 대신 캡·스폰으로 게이팅한다.
    cooldown: dict[str, float] = {}
    for cmd, col in _FREQ_COL.items():
        mean = float(df[col].mean())
        cd = (600.0 / mean) / COMPRESS if mean > 0 else 0.0
        cooldown[cmd] = cd if cd <= DURATION else 0.0
    spawn = {cmd: m * 60.0 / COMPRESS for cmd, m in SPAWN_MIN.items()}

    return Engine(coef=coef, intercept=intercept, reward=reward, unit_cap=unit_cap,
                  axis_cap=axis_cap, cooldown=cooldown, spawn=spawn, auc=auc)


# ---------------------------------------------------------------- 상태
@dataclass
class Side:
    gold: float = 0.0
    exp: float = 0.0
    counts: dict[str, int] = field(default_factory=dict)
    partial: float = 0.0                                  # N타 미완성 선지불 logit
    units: list[tuple[str, float]] = field(default_factory=list)
    progress: dict[str, int] = field(default_factory=dict)
    done: dict[str, int] = field(default_factory=dict)
    cd_until: dict[str, float] = field(default_factory=dict)
    rejected: list[tuple[str, str, float]] = field(default_factory=list)  # (명령어, 사유, 시각)
    queue_end: float = 0.0                                # 큐 처리 완료 예정 시각
    ends: list[float] = field(default_factory=list)       # 수락된 입력들의 완료시각
    hits: dict[str, int] = field(default_factory=dict)    # 오브젝트에 넣은 타격 수 (막타 못 치면 버려진다)
    stolen: list[str] = field(default_factory=list)       # 내가 때렸는데 상대가 가져간 것
    ward_expiry: list[float] = field(default_factory=list)  # 설치한 와드의 만료 시각
    sniped: list[float] = field(default_factory=list)     # 기습당한 시각
    swept: list[float] = field(default_factory=list)      # 상대 와드를 걷어낸 시각
    frozen_until: float = 0.0                             # 이 시각까지 입력 불가

    def remaining_cd(self, cmd: str, now: float) -> float:
        return max(0.0, self.cd_until.get(cmd, 0.0) - now)

    def in_system(self, now: float) -> int:
        return sum(1 for e in self.ends if e > now)

    def live_wards(self, now: float) -> int:
        """지금 살아 있는 와드 수. 와드는 WARD_DURATION 뒤 사라진다."""
        return sum(1 for t in self.ward_expiry if t > now)

    def has_vision(self, now: float) -> bool:
        """와드가 하나라도 살아 있으면 상대 큐가 보인다."""
        return self.live_wards(now) > 0


def new_hp() -> dict[str, int]:
    """경합 오브젝트의 **공유 체력**. 양쪽이 같은 체력을 깎고, 막타를 넣은 쪽이 가져간다."""
    return {c: s["n"] for c, s in COMMANDS.items() if s["contested"]}


def available(engine: Engine, me: Side, cmd: str, now: float,
              hp: dict[str, int]) -> tuple[bool, str]:
    """지금 이 명령을 칠 수 있는가. UI가 그대로 써서 실시간 표시한다."""
    if now >= DURATION:
        return False, R_TIME
    if now < me.frozen_until:
        return False, R_FROZEN
    if now < engine.spawn.get(cmd, 0.0):
        return False, R_SPAWN
    if me.remaining_cd(cmd, now) > 0:
        return False, R_COOLDOWN
    if COMMANDS[cmd]["contested"] and hp.get(cmd, 0) <= 0:
        return False, R_CAP                       # 이미 누군가 막타를 가져갔다
    if me.done.get(cmd, 0) >= engine.unit_cap[cmd]:
        return False, R_CAP
    if me.in_system(now) >= QUEUE_CAP:
        return False, R_QUEUE
    return True, ""


def simulate(p1: list[tuple[str, float]], p2: list[tuple[str, float]],
             engine: Engine, duration: float = DURATION) -> tuple[Side, Side, dict[str, int]]:
    """양쪽 큐를 하나의 시간축에서 동시에 처리한다.

    한 시간축에서 돌려야 하는 이유: `wardkill`은 **상대가 와드를 깔아놔야** 가능하고,
    드래곤·전령·퍼블은 **먼저 완성한 쪽만** 가져간다. 두 큐가 서로를 본다.
    """
    sides = {"p1": Side(), "p2": Side()}
    foe_of = {"p1": "p2", "p2": "p1"}
    hp = new_hp()

    events = sorted([(t, "p1", c) for c, t in p1] + [(t, "p2", c) for c, t in p2],
                    key=lambda x: (x[0], x[1]))
    pending: list[tuple[float, int, str, str]] = []       # (완료시각, 순번, who, cmd)
    seq = 0

    def complete(end: float, who: str, cmd: str) -> None:
        me = sides[who]
        spec = COMMANDS[cmd]
        n = spec["n"]
        own = engine.coef.get(spec["feature"], 0.0) if spec["feature"] else 0.0

        if spec["contested"]:
            # 공유 체력 — 양쪽 타격이 같은 체력을 깎는다. **막타를 넣은 쪽만** 가져간다.
            # 3대 때리고 막타를 뺏기면 그 3대는 그냥 버려진다 (실제 롤의 스틸).
            if hp.get(cmd, 0) <= 0:
                me.rejected.append((cmd, R_CAP, end))
                return
            hp[cmd] -= 1
            me.hits[cmd] = me.hits.get(cmd, 0) + 1
            if hp[cmd] > 0:
                return                                   # 아직 안 죽었다
            foe_side = sides[foe_of[who]]
            if foe_side.hits.get(cmd, 0):
                foe_side.stolen.append(cmd)              # 상대가 때렸는데 내가 막타
        else:
            me.progress[cmd] = me.progress.get(cmd, 0) + 1
            if me.progress[cmd] < n:
                if own < 0:
                    me.partial += own / (n - 1)
                return
            me.progress[cmd] = 0
            if own < 0 and n > 1:
                me.partial -= own                        # 선지불 되돌림 → 합계 보존
        if me.done.get(cmd, 0) >= engine.unit_cap[cmd]:
            me.rejected.append((cmd, R_CAP, end))
            return

        g, e = engine.reward[cmd]
        me.gold += g
        me.exp += e
        if spec["feature"]:
            me.counts[spec["feature"]] = me.counts.get(spec["feature"], 0) + 1
        me.units.append((cmd, end))
        me.done[cmd] = me.done.get(cmd, 0) + 1

        # 딸려오는 효과 (퍼블 → 킬). 캡을 넘지 않을 때만 준다.
        extra = spec.get("also")
        if extra and me.done.get(extra, 0) < engine.unit_cap[extra]:
            eg, ee = engine.reward[extra]
            me.gold += eg
            me.exp += ee
            ef = COMMANDS[extra]["feature"]
            if ef:
                me.counts[ef] = me.counts.get(ef, 0) + 1
            me.done[extra] = me.done.get(extra, 0) + 1
            me.units.append((extra, end))
            ecd = engine.cooldown.get(extra, 0.0)
            if ecd:                                  # 퍼블도 킬이므로 킬 쿨타임이 돈다
                me.cd_until[extra] = end + ecd
        if cmd == "ward":
            me.ward_expiry.append(end + WARD_DURATION)      # 시야 확보
        if cmd == DISRUPTOR:
            foe_side = sides[foe_of[who]]
            live = sorted(t for t in foe_side.ward_expiry if t > end)
            if live:
                # 상대가 시야를 갖고 있다 → 와드 1개만 걷어낸다. 기습은 실패.
                foe_side.ward_expiry.remove(live[0])
                me.swept.append(end)
            else:
                # 상대가 장님이다 → 기습 성공. FREEZE초간 입력 불가 (사망 리스폰).
                # 큐가 아니라 **시간**을 뺏는다. 전략은 유지되고 템포만 잃는다.
                foe_side.frozen_until = max(foe_side.frozen_until, end) + FREEZE
                foe_side.sniped.append(end)
        cd = engine.cooldown.get(cmd, 0.0)
        if cd:
            me.cd_until[cmd] = end + cd

    def flush(until: float) -> None:
        while pending and pending[0][0] <= until:
            end, sq, who, cmd = heapq.heappop(pending)
            complete(end, who, cmd)

    for t, who, cmd in events:
        if cmd not in COMMANDS:
            continue
        flush(t)
        me = sides[who]
        ok, why = available(engine, me, cmd, t, hp)
        if not ok:
            me.rejected.append((cmd, why, t))
            continue
        start = max(me.queue_end, t)
        end = start + COMMANDS[cmd]["sec"]
        if end > duration:
            me.rejected.append((cmd, R_TIME, t))
            continue
        me.queue_end = end
        me.ends.append(end)
        seq += 1
        heapq.heappush(pending, (end, seq, who, cmd))

    flush(duration)
    return sides["p1"], sides["p2"], hp


# ---------------------------------------------------------------- 승률
def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _terms(engine: Engine, mine: Side, theirs: Side) -> dict[str, float]:
    t: dict[str, float] = {}
    gc, ec = engine.axis_cap["goldDiff"], engine.axis_cap["expDiff"]
    t["goldDiff"] = engine.coef["goldDiff"] * _clip(mine.gold - theirs.gold, -gc, gc)
    t["expDiff"] = engine.coef["expDiff"] * _clip(mine.exp - theirs.exp, -ec, ec)
    for f in FEATURES:
        if f in AXIS:
            continue
        diff = mine.counts.get(f, 0) - theirs.counts.get(f, 0)
        if diff:
            t[f] = engine.coef[f] * diff
    partial = mine.partial - theirs.partial
    if partial:
        t["미완성 선지불"] = partial
    return t


LABEL = {
    "goldDiff": "골드 차", "expDiff": "경험치 차", "killDiff": "킬 차", "csDiff": "CS 차",
    "jungleDiff": "정글 차", "dragDiff": "드래곤", "heraldDiff": "전령",
    "towerDiff": "타워 차", "wardDiff": "와드 차", "wardKillDiff": "와드 제거 차",
    "firstBlood": "퍼블",
}


def win_rate(engine: Engine, mine: Side, theirs: Side,
             use_intercept: bool = False) -> dict:
    """{"score": int, "level": str, "reasons": list[str]} — 3단계까지 이 형식을 고정한다.

    use_intercept: 절편은 데이터의 **블루 진영 프리미엄**(+0.012)이다. 1대1에는 진영이
    없으므로 기본은 False다. 꺼야 sigmoid(s)+sigmoid(-s)=1 이라 양쪽 합이 정확히 100이 된다.
    """
    terms = _terms(engine, mine, theirs)
    logit = (engine.intercept if use_intercept else 0.0) + sum(terms.values())
    p = 1.0 / (1.0 + math.exp(-_clip(logit, -30.0, 30.0)))
    score = int(round(p * 100))
    level = "불리"
    for cut, name in LEVELS:
        if score >= cut:
            level = name
            break
    reasons = []
    for key, contrib in sorted(terms.items(), key=lambda kv: -abs(kv[1])):
        if abs(contrib) < 1e-6:
            continue
        without = 1.0 / (1.0 + math.exp(-_clip(logit - contrib, -30.0, 30.0)))
        reasons.append(f"{LABEL.get(key, key)} ({contrib:+.3f} logit, {(p - without) * 100:+.1f}%p)")
    if not reasons:
        reasons.append("아직 아무 영향 없음 (50% 출발)")
    return {"score": score, "level": level, "reasons": reasons}


def battle(p1: list[tuple[str, float]], p2: list[tuple[str, float]],
           engine: Engine, duration: float = DURATION) -> dict:
    a, b, hp = simulate(p1, p2, engine, duration)
    r1, r2 = win_rate(engine, a, b), win_rate(engine, b, a)
    return {"p1": r1, "p2": r2, "side1": a, "side2": b, "hp": hp,
            "winner": "p1" if r1["score"] > r2["score"] else
                      ("p2" if r2["score"] > r1["score"] else "draw")}


def rate_limit(presses: list[tuple[str, float]], gap: float = MIN_GAP):
    """측정 기반 레이트 리밋. 0.20초 미만 간격은 서버에서 조용히 유실된다
    (측정: 0ms→95% 유실, 50ms→45%, 200ms→0%). 여기서 명시적으로 거부한다."""
    kept, rejected = [], []
    last = -1e9
    for cmd, t in presses:
        if t - last < gap:
            rejected.append((cmd, t))
        else:
            kept.append((cmd, t))
            last = t
    return kept, rejected


def _marginal(engine: Engine, cmd: str, gold: float, exp: float) -> float:
    """현재 상태에서 이 명령을 하나 더 완성했을 때 실제로 늘어나는 logit.
    축 캡에 닿으면 이득이 0이 되므로 포화가 자동으로 반영된다."""
    g, e = engine.reward[cmd]
    gc, ec = engine.axis_cap["goldDiff"], engine.axis_cap["expDiff"]
    before = engine.coef["goldDiff"] * _clip(gold, -gc, gc) + engine.coef["expDiff"] * _clip(exp, -ec, ec)
    after = engine.coef["goldDiff"] * _clip(gold + g, -gc, gc) + engine.coef["expDiff"] * _clip(exp + e, -ec, ec)
    spec = COMMANDS[cmd]
    own = engine.coef.get(spec["feature"], 0.0) if spec["feature"] else 0.0
    return (after - before) + own


def suggest_sequence(engine: Engine, duration: float = DURATION,
                     skip: tuple[str, ...] = ()) -> list[str]:
    """쿨타임·스폰을 고려해 '지금 칠 수 있는 것 중 한계이득이 가장 큰 것'을 계속 고른다.

    쿨타임이 생긴 뒤로는 고정 배분(몇 개씩)이 의미가 없다 — 타이밍이 전략이다.
    그래서 개수가 아니라 **순서**를 돌려준다.

    ponytail: 탐욕 정책. 상대 반응을 보지 않으므로 진짜 최적은 아니다.
    """
    me = Side()
    hp = new_hp()
    out: list[str] = []
    now = 0.0
    gold = exp = 0.0
    while now < duration:
        best, best_rate = None, 1e-9
        for cmd in COMMANDS:
            if cmd in skip:
                continue
            ok, _ = available(engine, me, cmd, now, hp)
            if not ok:
                continue
            cost = COMMANDS[cmd]["n"] * COMMANDS[cmd]["sec"]
            rate = _marginal(engine, cmd, gold, exp) / cost
            if rate > best_rate:
                best, best_rate = cmd, rate
        if best is None:
            # 전부 쿨타임이면 가장 빨리 풀리는 때로 시간을 넘긴다
            waits = [me.remaining_cd(c, now) for c in COMMANDS if me.remaining_cd(c, now) > 0]
            spawns = [engine.spawn[c] - now for c in engine.spawn if engine.spawn[c] > now]
            step = min(waits + spawns) if (waits or spawns) else duration
            now += max(step, 0.05)
            continue
        spec = COMMANDS[best]
        out += [best] * spec["n"]
        now += spec["n"] * spec["sec"]
        g, e = engine.reward[best]
        gold += g
        exp += e
        me.done[best] = me.done.get(best, 0) + 1
        if spec["contested"]:
            hp[best] = 0            # 혼자 치는 가정이므로 막타도 내가 가져간다
        cd = engine.cooldown.get(best, 0.0)
        if cd:
            me.cd_until[best] = now + cd
    return out


# ---------------------------------------------------------------- 대결 방 (파일 공유)
# 두 기기가 파일 몇 개로 같은 방을 본다. **각자 자기 파일만 쓴다** — 동시 쓰기 경합이 구조적으로 없다.
#   room.json  초대(invite) 시각·게임 길이 ← 신청한 쪽 / accept_P1·P2.json ← 각자 / p1·p2.jsonl ← 각자 append
# 시작 시각은 아무도 쓰지 않는다: max(수락 시각) + COUNTDOWN을 양쪽이 각자 계산한다.
COUNTDOWN = 3.0          # 양쪽 수락 후 시작까지 (롤 매칭 수락 뒤 로딩에 해당)
SLOTS = ("P1", "P2")


def _presses_file(room: Path, slot: str) -> Path:
    return room / f"{slot.lower()}.jsonl"


def _accept_file(room: Path, slot: str) -> Path:
    return room / f"accept_{slot}.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def read_presses(room: Path, slot: str, until: float = math.inf) -> list[tuple[str, float]]:
    """until초까지의 입력. 반쯤 쓰인 줄은 건너뛴다 — 다음 폴링에 다시 읽힌다."""
    path = _presses_file(room, slot)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            d = json.loads(line)
            out.append((d["cmd"], float(d["t"])))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return [(c, t) for c, t in out if t <= until]


def append_press(room: Path, slot: str, cmd: str, t: float) -> None:
    """O_APPEND 한 줄 쓰기. 자기 파일만 쓰므로 경합이 없다."""
    with _presses_file(room, slot).open("a") as f:
        f.write(json.dumps({"cmd": cmd, "t": round(t, 3)}) + "\n")


def _room_files(room: Path) -> list[Path]:
    return [room / "room.json"] + [f(room, s) for s in SLOTS for f in (_presses_file, _accept_file)]


def clear_room(room: Path) -> None:
    for p in _room_files(room):
        p.unlink(missing_ok=True)


def invite(room: Path, duration: float = DURATION) -> None:
    """대결 신청 — 이전 수락·입력을 지우고 새 invite를 연다."""
    clear_room(room)
    (room / "room.json").write_text(json.dumps({"invite": time.time(), "duration": duration}))


def accept(room: Path, slot: str, invite_id: float) -> None:
    """수락 — 자기 파일만 쓴다. invite_id로 묶어 지난 경기의 수락이 섞이지 않게 한다."""
    _accept_file(room, slot).write_text(json.dumps({"invite": invite_id, "at": time.time()}))


def read_state(room: Path) -> dict:
    """현재 방 상태를 **파일에서만** 계산한다. 양쪽이 같은 값을 얻는다.

    phase: idle(신청 전) → lobby(수락 대기) → countdown → playing → over
    """
    r = _read_json(room / "room.json")
    inv = r.get("invite")
    duration = float(r.get("duration", DURATION))
    accepted = {}
    for slot in SLOTS:
        a = _read_json(_accept_file(room, slot))
        if inv is not None and a.get("invite") == inv:
            accepted[slot] = float(a["at"])
    if inv is None or len(accepted) < 2:
        return {"phase": "idle" if inv is None else "lobby", "invite": inv, "duration": duration,
                "accepted": accepted, "started_at": None}
    started = max(accepted.values()) + COUNTDOWN       # 아무도 쓰지 않는 유도값
    now = time.time()
    phase = ("countdown" if now < started
             else "playing" if now < started + duration else "over")
    return {"phase": phase, "invite": inv, "duration": duration,
            "accepted": accepted, "started_at": started}

"""봇 자동 대결 — 타자 속도(타/분) × 전략별 승률을 집계한다.

streamlit·브라우저 없이 core.py만 쓴다. 실행: python bot_test.py [게임수]

타자 속도는 **타/분(KPM)** 이다. 명령어마다 글자 수가 달라서 치는 데 걸리는 시간이 다르다
(`cs` 3타 vs `firstblood` 11타). 짧은 명령이 빠르다는 점이 그대로 전략에 들어간다.
"""

import random
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

import core

# 150~550 타/분, 50단위 9개 케이스. (150~500은 8개라 550을 더해 9개로 맞췄다.)
KPM_CASES = list(range(150, 551, 50))
JITTER = 0.20          # 사람은 일정하지 않다 — 간격의 ±20% 흔들림


def keystrokes(cmd: str) -> int:
    """명령어 한 번 = 글자 수 + Enter."""
    return len(cmd) + 1


def seconds_for(cmd: str, kpm: float) -> float:
    return keystrokes(cmd) / (kpm / 60.0)


# ---------------------------------------------------------------- 전략
def strat_suggest(engine):
    """쿨타임·스폰을 보고 한계이득이 큰 것을 계속 고르는 정석."""
    return core.suggest_sequence(engine)


def strat_short_words(engine):
    """글자 수가 짧은 명령 위주 — 느린 타자가 타수를 버는 전략."""
    cheap = sorted(core.COMMANDS, key=keystrokes)[:4]
    seq = []
    for i in range(400):
        seq.append(cheap[i % len(cheap)])
    return seq


def strat_objective(engine):
    """오브젝트 선점 최우선. 스폰 전까지는 골드."""
    return (["gold"] * 48 + ["dragon"] * core.COMMANDS["dragon"]["n"]
            + ["gold"] * 40 + ["herald"] * core.COMMANDS["herald"]["n"] + ["gold"] * 200)


def strat_tower_rush(engine):
    return ["tower"] * (4 * core.COMMANDS["tower"]["n"]) + ["gold"] * 300


def strat_kill_cycle(engine):
    """kill 쿨타임(9.7초)에 맞춰 돌리고 사이사이 골드."""
    seq = []
    for _ in range(7):
        seq += ["kill"] * core.COMMANDS["kill"]["n"] + ["gold"] * 12
    return seq


def strat_spam(cmd):
    def f(engine):
        return [cmd] * 400
    f.__name__ = f"spam_{cmd}"
    return f


def strat_vision(engine):
    """시야+기습. 와드를 깔아 시야를 유지하고, 쿨타임마다 상대 큐를 끊는다.
    ward 쿨 2.69초 / wardkill 쿨 21.24초라 사이사이는 골드로 채운다."""
    seq = []
    for _ in range(3):                       # wardkill 쿨타임 주기 3회
        seq += ["ward"] + ["gold"] * 6 + ["wardkill"] + ["gold"] * 10
    return seq + ["gold"] * 200


def strat_disrupt_only(engine):
    """기습만 노리는 극단 전략 — 과한지 확인하는 대조군."""
    return (["ward", "wardkill"] * 100)


def strat_random(engine):
    cmds = list(core.COMMANDS)
    return [random.choice(cmds) for _ in range(400)]


STRATEGIES = {
    "정석(쿨타임순)": strat_suggest,
    "오브젝트선점": strat_objective,
    "킬사이클": strat_kill_cycle,
    "타워러시": strat_tower_rush,
    "짧은단어": strat_short_words,
    "골드몰빵": strat_spam("gold"),
    "레벨몰빵": strat_spam("level"),
    "시야+기습": strat_vision,
    "기습만": strat_disrupt_only,
    "무작위": strat_random,
}


def type_presses(seq, kpm, rng, duration=core.DURATION):
    """타/분대로 입력 시각을 만든다. 큐가 꽉 차면 사람처럼 같은 명령을 다시 시도한다."""
    out, ends = [], []
    prev_end = 0.0
    t = 0.0
    i = 0
    while i < len(seq) and t < duration:
        cmd = seq[i]
        t += seconds_for(cmd, kpm) * rng.uniform(1 - JITTER, 1 + JITTER)
        if t >= duration:
            break
        if sum(1 for e in ends if e > t) >= core.QUEUE_CAP:
            continue                        # 거부 — i를 늘리지 않고 재시도
        prev_end = max(prev_end, t) + core.SEC
        ends.append(prev_end)
        out.append((cmd, t))
        i += 1
    kept, _ = core.rate_limit(out)
    return kept


def main():
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    engine = core.fit_engine(pd.read_csv(Path(__file__).parent / "data" / "high_diamond_ranked_10min.csv"))
    print(f"엔진 AUC {engine.auc:.4f} | SEC {core.SEC}초 | 큐 {core.QUEUE_CAP}칸 | {games}판씩")
    print("쿨타임: " + " · ".join(f"{k} {v:.2f}초" for k, v in engine.cooldown.items() if v))
    print("스폰:   " + " · ".join(f"{k} {v:.0f}초" for k, v in engine.spawn.items()))

    print("\n" + "=" * 86)
    print("1. 타자 속도(타/분)별 단독 점수 — 전략은 '정석' 고정, 상대 없음")
    print("=" * 86)
    print(f"  {'타/분':>6}{'명령 수':>9}{'완성':>7}{'쿨거부':>8}{'미스폰':>8}{'점수':>7}   비고")
    seq = strat_suggest(engine)
    best_solo = (0, 0)
    for kpm in KPM_CASES:
        rng = random.Random(5)
        tot = Counter()
        score = 0.0
        for _ in range(games):
            pr = type_presses(seq, kpm, rng)
            r = core.battle(pr, [], engine)
            s = r["side1"]
            tot["cmds"] += len(pr)
            tot["units"] += len(s.units)
            tot["cd"] += sum(1 for _c, w, _t in s.rejected if w == core.R_COOLDOWN)
            tot["sp"] += sum(1 for _c, w, _t in s.rejected if w == core.R_SPAWN)
            score += r["p1"]["score"]
        avg = score / games
        if avg > best_solo[1]:
            best_solo = (kpm, avg)
        print(f"  {kpm:>6}{tot['cmds']/games:>9.1f}{tot['units']/games:>7.1f}"
              f"{tot['cd']/games:>8.1f}{tot['sp']/games:>8.1f}{avg:>7.1f}")
    print(f"\n  → 단독 점수 최고: {best_solo[0]}타/분 ({best_solo[1]:.1f}점)")

    print("\n" + "=" * 86)
    print("2. 타자 속도 맞대결 (양쪽 '정석') — 행의 평균 점수")
    print("=" * 86)
    print("  승률은 1점 차나 40점 차나 똑같이 100%라 정보가 없다. 점수로 본다 (50=호각).")
    print("       " + "".join(f"{k:>7}" for k in KPM_CASES))
    for a in KPM_CASES:
        row = []
        for bkpm in KPM_CASES:
            if a == bkpm:
                row.append("    -  ")
                continue
            rng = random.Random(13)
            n = max(30, games // 4)
            s = 0.0
            for _ in range(n):
                p1 = type_presses(seq, a, rng)
                p2 = type_presses(seq, bkpm, rng)
                s += core.battle(p1, p2, engine)["p1"]["score"]
            row.append(f"{s / n:6.1f} ")
        print(f"  {a:>5}" + "".join(row))
    print("  (행=내 타/분, 값=행의 평균 승률 점수)")

    print("\n  인접 구간(+50타/분)의 실제 격차:")
    for i in range(len(KPM_CASES) - 1):
        a, bkpm = KPM_CASES[i], KPM_CASES[i + 1]
        rng = random.Random(13)
        n = max(30, games // 4)
        s = 0.0
        for _ in range(n):
            s += core.battle(type_presses(seq, bkpm, rng), type_presses(seq, a, rng), engine)["p1"]["score"]
        print(f"    {bkpm} vs {a}: {s / n:5.1f}점  (격차 {s / n - 50:+.1f})")

    print("\n" + "=" * 86)
    print("3. 전략별 승률 (타/분별 라운드로빈)")
    print("=" * 86)
    winner_by_kpm = {}
    for kpm in (KPM_CASES[0], KPM_CASES[len(KPM_CASES) // 2], KPM_CASES[-1]):
        print(f"\n  [{kpm} 타/분]")
        table = {}
        for a in STRATEGIES:
            rng = random.Random(17)
            wins = plays = 0
            per = max(5, games // (len(STRATEGIES) - 1))
            for bname in STRATEGIES:
                if a == bname:
                    continue
                for _ in range(per):
                    p1 = type_presses(STRATEGIES[a](engine), kpm, rng)
                    p2 = type_presses(STRATEGIES[bname](engine), kpm, rng)
                    r = core.battle(p1, p2, engine)
                    wins += 1 if r["winner"] == "p1" else (0.5 if r["winner"] == "draw" else 0)
                    plays += 1
            table[a] = wins / plays * 100
        winner_by_kpm[kpm] = max(table, key=lambda k: table[k])
        for a, v in sorted(table.items(), key=lambda kv: -kv[1]):
            print(f"    {a:<16} {v:5.1f}%  {'█' * int(v / 2.5)}")
    print(f"\n  타/분별 1위 전략: {winner_by_kpm}")

    print("\n" + "=" * 86)
    print("4. 느린 타자가 전략으로 빠른 타자를 이길 수 있는가")
    print("=" * 86)
    for slow, fast in [(KPM_CASES[0], KPM_CASES[-1]), (300, 350), (250, 350)]:
        print(f"\n  ({slow}타/분 + 전략 X)  vs  ({fast}타/분 + 골드몰빵)")
        rows = []
        for sname, fn in STRATEGIES.items():
            rng = random.Random(29)
            s = 0.0
            w = Counter()
            for _ in range(games):
                p1 = type_presses(fn(engine), slow, rng)
                p2 = type_presses(STRATEGIES["골드몰빵"](engine), fast, rng)
                r = core.battle(p1, p2, engine)
                s += r["p1"]["score"]
                w[r["winner"]] += 1
            rows.append((sname, s / games, (w["p1"] + 0.5 * w["draw"]) / games * 100))
        for sname, sc, wr in sorted(rows, key=lambda x: -x[1]):
            print(f"    {sname:<16} 점수 {sc:5.1f}  승률 {wr:5.1f}%")


if __name__ == "__main__":
    main()

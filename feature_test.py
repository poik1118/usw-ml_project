"""기획서 피드백 3-2 검증 — 골드 통제 시 부호가 뒤집히는 피처를 상호작용·비율로 재설계하면 나아지는가.

실행: python feature_test.py        (약 1분)
결과는 docs/모델검증.md "피드백 검증 — 골드 통제 피처 재설계" 표에 옮겨 두었다.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import core

df = pd.read_csv("data/high_diamond_ranked_10min.csv")
y = df["blueWins"].to_numpy()
base = core.features(df)


def per_gold(blue, red):
    """팀별 '1,000골드당 X'의 차. 각 팀 총골드가 최소 10,730이라 0으로 나눌 일이 없다."""
    return blue / df.blueTotalGold * 1000 - red / df.redTotalGold * 1000


g = base.goldDiff
ratios = {
    "kpg": per_gold(df.blueKills, df.redKills),
    "tpg": per_gold(df.blueTowersDestroyed, df.redTowersDestroyed),
    "cpg": per_gold(df.blueTotalMinionsKilled, df.redTotalMinionsKilled),
    "jpg": per_gold(df.blueTotalJungleMinionsKilled, df.redTotalJungleMinionsKilled),
}
FLIPPED = ["killDiff", "towerDiff", "csDiff", "jungleDiff"]
VARIANTS = {
    "기준 (현재 11피처)": base,
    "+ 상호작용 4종 (kill·tower·cs·jungle × gold)": base.assign(
        **{f"{f}×gold": base[f] * g for f in FLIPPED}),
    "+ 골드당 킬": base.assign(kpg=ratios["kpg"]),
    "+ 골드당 킬·타워·CS": base.assign(**{k: ratios[k] for k in ("kpg", "tpg", "cpg")}),
    "뒤집히는 4종을 골드당 비율로 교체": base.drop(columns=FLIPPED).assign(**ratios),
    "(참고) 골드 1피처만": base[["goldDiff"]],
}


def model():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000))


def main() -> None:
    splits = list(RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=0).split(base, y))
    auc, acc = {}, {}
    for name, X in VARIANTS.items():
        Xv = X.to_numpy(float)
        a, c = [], []
        for tr, te in splits:
            p = model().fit(Xv[tr], y[tr]).predict_proba(Xv[te])[:, 1]
            a.append(roc_auc_score(y[te], p))
            c.append(accuracy_score(y[te], p > 0.5))
        auc[name], acc[name] = np.array(a), np.array(c)

    ref = "기준 (현재 11피처)"

    print(f"5-fold × 10회 = {len(splits)}개 분할 · 모든 변형이 같은 분할에서 쌍체 비교\n")
    print(f"| 변형 | AUC | Δ AUC (평균 ± 표준편차) | 정확도 | Δ 정확도 |")
    print("|---|---|---|---|---|")
    for name in VARIANTS:
        d, da = auc[name] - auc[ref], acc[name] - acc[ref]
        print(f"| {name} | {auc[name].mean():.5f} | {d.mean():+.5f} ± {d.std():.5f} "
              f"| {acc[name].mean() * 100:.2f}% | {da.mean() * 100:+.2f}%p |")

    # 상호작용 항을 넣으면 부호 뒤집힘이 사라지는가 — 전체 데이터 적합 후 원단위 계수
    X = VARIANTS["+ 상호작용 4종 (kill·tower·cs·jungle × gold)"]
    m = model().fit(X, y)
    coef = dict(zip(X.columns, m[-1].coef_[0] / m[0].scale_))
    print("\n상호작용을 넣은 뒤 주효과 계수:", ", ".join(f"{f} {coef[f]:+.4f}" for f in FLIPPED))


if __name__ == "__main__":
    main()

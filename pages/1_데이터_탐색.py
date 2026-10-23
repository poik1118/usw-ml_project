"""화면 1 — 원본 데이터 탐색. 왜 계수가 음수인지 눈으로 확인한다."""

import numpy as np
import pandas as pd
import streamlit as st

import core
from shared import engine_or_stop, load_data

st.title("데이터 탐색", text_alignment="center")
st.caption("League of Legends Diamond Ranked Games (10 min) · 9,879경기 × 40열 · 결측치 0",
           text_alignment="center")

df = load_data()
engine = engine_or_stop()



tab_basic, tab_coef, tab_control, tab_cols = st.tabs(
    ["기본", "계수 부호", "골드 통제 비교", "열 목록"]
)

with tab_basic:
    c = st.container(horizontal=True)
    c.metric("경기 수", f"{len(df):,}", border=True)
    c.metric("블루 승률", f"{df['blueWins'].mean() * 100:.1f}%", border=True)
    c.metric("모델 AUC `Higher is better`", f"{engine.auc:.4f}", border=True)

    st.subheader("골드 차이 → 승률")
    bins = pd.cut(df["blueGoldDiff"], range(-11000, 12000, 1000))
    curve = df.groupby(bins, observed=True)["blueWins"].agg(["mean", "size"])
    curve = curve[curve["size"] >= 30]
    chart = pd.DataFrame({
        "골드 차": [int(i.mid) for i in curve.index],
        "실제 승률": (curve["mean"] * 100).to_numpy(),
    }).set_index("골드 차")
    st.line_chart(chart, y="실제 승률")

    st.subheader("명령어별 데이터 평균 빈도 (10분, 한 팀)")
    freq = {
        "cs": df["blueTotalMinionsKilled"].mean(), "jungle": df["blueTotalJungleMinionsKilled"].mean(),
        "ward": df["blueWardsPlaced"].mean(), "wardkill": df["blueWardsDestroyed"].mean(),
        "kill": df["blueKills"].mean(), "firstblood": df["blueFirstBlood"].mean(),
        "dragon": df["blueDragons"].mean(), "herald": df["blueHeralds"].mean(),
        "tower": df["blueTowersDestroyed"].mean(),
    }
    st.dataframe(
        [{"명령어": k, "10분 평균": round(v, 3), "실제 1회당 초": round(600 / v, 1) if v else None,
          "cs 대비 희소": round(freq["cs"] / v, 1) if v else None}
         for k, v in sorted(freq.items(), key=lambda kv: -kv[1])],
        hide_index=True,
    )
    st.info(
        "타워는 실제로 10분에 0.05개만 깨진다 — **cs보다 4,200배 희소**하다. \n\n"
        "60초 1대1 게임에 10분 5대5의 희소 이벤트를 담으려면 시간 압축이 불가피하다. \n\n"
        "그래서 `N타`만은 데이터가 정해줄 수 없는 설계 변수다.",
        icon=":material/compress:",
    )

with tab_coef:
    st.subheader("계수 부호 — 음수가 5개다 (wardDiff는 ≈0)")
    rows = []
    feats = core.features(df)
    for f in core.FEATURES:
        rows.append({
            "피처": f,
            "raw 계수": round(engine.coef[f], 7),
            "blueWins 단독 상관": round(float(feats[f].corr(df["blueWins"])), 3),
            "부호": "음수" if engine.coef[f] < 0 else "양수",
        })
    st.dataframe(rows, hide_index=True)
    st.warning(
        "`killDiff` `csDiff` `towerDiff` `jungleDiff`는 **단독 상관은 양수인데 계수는 음수**다. "
        "셋 다 골드의 대리변수라서, 골드차를 통제하면 "
        "'같은 골드인데 타워를 깼다 = 타워 말고는 다 밀렸다'가 되어 부호가 뒤집힌다.",
        icon=":material/swap_vert:",
    )
    st.caption(
        "이 게임은 이 음수를 숨기지 않는다. 다타 명령은 완성 전까지 음수를 선지불하고, "
        "완성 시 골드·경험 보상이 들어와 합계가 데이터의 순효과와 정확히 일치한다."
    )

    st.subheader("tower 5타 승률 궤적")
    traj = []
    for k in range(core.COMMANDS["tower"]["n"] + 1):
        presses = [("tower", i * (core.SEC + 0.1)) for i in range(k)]
        traj.append({
            "타수": k,
            "승률": core.battle(presses, [], engine)["p1"]["score"],
        })
    st.bar_chart(pd.DataFrame(traj).set_index("타수"), y="승률")
    st.caption("4타까지 내려가다 5타에서 뒤집힌다. 임의로 만든 숫자가 하나도 없다.")

with tab_control:
    st.subheader("골드차를 통제하면 킬·드래곤은 어떻게 되나")
    d = df.assign(
        killDiff=df["blueKills"] - df["blueDeaths"],
        dragDiff=df["blueDragons"] - df["redDragons"],
        gbin=pd.cut(df["blueGoldDiff"],
                    [-np.inf, -2500, -1000, -300, 300, 1000, 2500, np.inf],
                    labels=["<-2500", "-2500~-1000", "-1000~-300", "-300~300",
                            "300~1000", "1000~2500", ">2500"]),
    )
    mode = st.segmented_control("비교 대상", ["킬 우위", "드래곤 선취"], default="킬 우위")
    out = []
    for gb, g in d.groupby("gbin", observed=True):
        if mode == "킬 우위":
            groups = {"열세(-2 이하)": g[g["killDiff"] <= -2],
                      "호각(±1)": g[g["killDiff"].abs() <= 1],
                      "우위(+2 이상)": g[g["killDiff"] >= 2]}
        else:
            groups = {"내줌": g[g["dragDiff"] == -1], "없음": g[g["dragDiff"] == 0],
                      "먹음": g[g["dragDiff"] == 1]}
        row = {"골드차 구간": str(gb)}
        for name, sub in groups.items():
            row[name] = round(sub["blueWins"].mean() * 100, 1) if len(sub) >= 30 else None
        row["표본"] = len(g)
        out.append(row)
    st.dataframe(out, hide_index=True)
    if mode == "킬 우위":
        st.caption("골드차를 고정하면 킬 우위의 추가 효과가 거의 없다. 킬 골드가 이미 골드차에 들어있다.")
    else:
        st.caption("골드차가 같아도 드래곤을 먹은 쪽이 일관되게 높다. 드래곤은 골드 밖 경로로 작동한다.")

    anom = d[(d["killDiff"] >= 3) & (d["blueGoldDiff"] < 0)]
    norm = d[(d["killDiff"] >= 3) & (d["blueGoldDiff"] >= 0)]
    cc = st.container(horizontal=True)
    cc.metric("킬 +3 이상 & 골드 앞섬", f"{norm['blueWins'].mean() * 100:.1f}%",
              f"n={len(norm):,}", border=True)
    cc.metric("킬 +3 이상 & 골드 뒤짐", f"{anom['blueWins'].mean() * 100:.1f}%",
              f"n={len(anom)}", delta_color="inverse", border=True)
    st.caption("킬을 3개 더 했는데도 골드가 뒤지면 승률이 50% 아래로 내려간다.")

with tab_cols:
    st.subheader("중복 열 — 40열 중 실질 정보는 11개")
    st.code(
        "redGoldDiff          == -blueGoldDiff              (전 행 일치)\n"
        "blueDeaths           == redKills                   (전 행 일치)\n"
        "blueCSPerMin         == blueTotalMinionsKilled/10  (전 행 일치)\n"
        "blueEliteMonsters    == blueDragons + blueHeralds  (전 행 일치)\n"
        "blueFirstBlood + redFirstBlood == 1                (전 행 일치)",
        language="text",
    )
    st.caption("40열을 그대로 넣으면 완전 공선성으로 계수가 무의미해진다. diff 11개로 줄여야 한다.")
    st.dataframe(
        [{"열": c, "타입": str(df[c].dtype), "최소": df[c].min(), "최대": df[c].max(),
          "평균": round(float(df[c].mean()), 2)} for c in df.columns],
        hide_index=True, height=400,
    )

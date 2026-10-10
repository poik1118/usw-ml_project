"""화면 1 · 데이터 탐색 — 로드(캐시) → 필터 → 지표 → 차트"""
import pandas as pd
import streamlit as st

st.title("데이터 탐색")


@st.cache_data                      # 같은 파일은 다시 읽지 않는다 (위젯을 만질 때마다 스크립트가 재실행되므로)
def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    return df


up = st.sidebar.file_uploader("다른 CSV 올리기 (선택)", type="csv")
df = pd.read_csv(up) if up is not None else load("data/telco_churn.csv")

with st.sidebar:
    contracts = st.multiselect("계약 유형", sorted(df["Contract"].unique()), default=list(df["Contract"].unique()))
    t_min, t_max = st.slider("가입 개월", 0, int(df["tenure"].max()), (0, int(df["tenure"].max())))

view = df[df["Contract"].isin(contracts) & df["tenure"].between(t_min, t_max)]
churn_rate = (view["Churn"] == "Yes").mean() if len(view) else 0.0

c1, c2, c3 = st.columns(3)
c1.metric("고객 수", f"{len(view):,}")
c2.metric("이탈률", f"{churn_rate:.1%}")
c3.metric("평균 월요금", f"${view['MonthlyCharges'].mean():.1f}" if len(view) else "-")

st.subheader("계약 유형별 이탈률")
rate = view.groupby("Contract")["Churn"].apply(lambda s: (s == "Yes").mean()).rename("이탈률")
st.bar_chart(rate)

st.subheader("가입 기간별 이탈률")
bins = pd.cut(view["tenure"], [-1, 6, 12, 24, 48, 72], labels=["0-6", "7-12", "13-24", "25-48", "49-72"])
st.bar_chart(view.groupby(bins, observed=True)["Churn"].apply(lambda s: (s == "Yes").mean()).rename("이탈률"))

with st.expander("필터된 원본 보기"):
    st.dataframe(view, width="stretch")

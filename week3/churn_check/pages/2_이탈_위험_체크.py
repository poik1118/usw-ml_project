"""화면 2 · 이탈 위험 체크 — 입력 폼 → (가짜 백엔드) → 결과 + 이력(session_state)"""
from datetime import datetime

import pandas as pd
import streamlit as st
from core import churn_score

st.title("이탈 위험 체크")

if "history" not in st.session_state:      # 재실행돼도 살아남는 저장소
    st.session_state.history = []
if "last" not in st.session_state:         # 마지막 결과. 버튼 밖에서 그리려고 보관한다
    st.session_state.last = None

with st.form("check"):                     # 폼: 제출 버튼을 누를 때만 한 번 실행
    c1, c2 = st.columns(2)
    contract = c1.selectbox("계약 유형", ["Month-to-month", "One year", "Two year"])
    tenure = c1.number_input("가입 개월", 0, 72, 3)
    monthly = c2.number_input("월요금 ($)", 18.0, 120.0, 85.0, step=0.5)
    internet = c2.selectbox("인터넷", ["DSL", "Fiber optic", "No"])
    support = st.radio("기술지원 가입", ["Yes", "No"], horizontal=True)
    submitted = st.form_submit_button("위험도 계산")

if submitted:                              # 제출 때는 계산·저장만 한다
    st.session_state.last = churn_score(contract, int(tenure), float(monthly), internet, support)
    st.session_state.history.append({
        "조회시각": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),   # 캐시 금지 대상이라 함수로 감싸지 않음
        "계약": contract, "개월": tenure, "월요금": monthly,
        "점수": st.session_state.last["score"], "수준": st.session_state.last["level"],
    })

if st.session_state.last:                  # 버튼 블록 밖 → 다른 위젯을 눌러도 결과가 남는다
    r = st.session_state.last
    color = {"높음": "red", "보통": "orange", "낮음": "green"}[r["level"]]
    st.markdown(f"### 위험 점수 **{r['score']}** / 100 — :{color}[{r['level']}]")
    st.progress(r["score"] / 100)
    for why in r["reasons"]:
        st.write("•", why)
    if r["score"] >= 70:                   # 고위험 → 쿠폰 대상
        st.error("리텐션 쿠폰 대상", icon=":material/local_activity:")

if st.session_state.history:
    st.subheader(f"이번 세션 조회 이력 ({len(st.session_state.history)}건)")
    hist = pd.DataFrame(st.session_state.history)
    st.dataframe(hist, width="stretch")
    with st.container(horizontal=True):
        st.download_button(
            "CSV 내려받기",
            data=hist.to_csv(index=False).encode("utf-8-sig"),   # 엑셀에서 한글 안 깨지게
            file_name=f"churn_history_{datetime.now():%Y%m%d_%H%M}.csv",
            mime="text/csv",
            icon=":material/download:",
        )
        if st.button("이력 지우기"):
            st.session_state.history = []
            st.rerun()

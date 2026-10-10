"""3주차 프로토타입 · 이탈 위험 체크 서비스 — 홈 화면
실행: streamlit run app.py   (pages/ 폴더의 파일이 자동으로 왼쪽 메뉴에 붙는다)
"""
import streamlit as st

st.set_page_config(page_title="이탈 위험 체크", page_icon="📉", layout="wide")

st.title("이탈 위험 체크 서비스 (프로토타입)")
st.markdown(
    """
**누구를 위한 서비스인가** — 통신사 고객관리팀. 고객 정보를 넣으면 이탈 위험을 알려 주고,
전체 데이터를 탐색할 수 있다.

**화면 구성**
1. 데이터 탐색 — 고객 데이터 필터·차트
2. 이탈 위험 체크 — 고객 정보 입력 → 위험 점수와 근거
3. 소개 — 문제·사용자·데이터 출처·AI 활용 기록
"""
)
c1, c2 = st.columns(2)
with c1:
    st.info("왼쪽 메뉴에서 화면을 고르세요.")
with c2:
    st.warning("현재 점수는 규칙 기반 프로토타입입니다. 2단계에서 학습한 ML 모델로 교체됩니다.")

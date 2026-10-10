"""화면 3 · 소개 — 문제·사용자·데이터 출처·AI 활용 기록 (읽기 전용 문서 화면)"""
import pandas as pd
import streamlit as st

# AI에게 무엇을 시켰고 결과를 어떻게 확인했는지. 작업할 때마다 한 줄 추가한다.
AI_LOG = [
    {
        "주차": "3주차",
        "시킨 일": "화면 2 — 점수 70 이상이면 '리텐션 쿠폰 대상' 표시",
        "결과": "pages/2_이탈_위험_체크.py에 st.error 한 줄",
        "확인 방법": "폼 기본값 85점 → 표시됨 / Two year·40개월 10점 → 안 뜸",
    },
    {
        "주차": "3주차",
        "시킨 일": "화면 2 — 이력 표에 조회 시각 열 추가",
        "결과": "datetime.now()를 '%Y-%m-%d %H:%M:%S' 문자열로 첫 열에 기록",
        "확인 방법": "표 출력 확인. 서버 시계가 하루 느린 것은 서버 설정 문제로 남겨 둠",
    },
    {
        "주차": "3주차",
        "시킨 일": "화면 2 — 이력 CSV 내려받기 버튼",
        "결과": "st.download_button + utf-8-sig (엑셀 한글 깨짐 방지)",
        "확인 방법": "BOM(\\xef\\xbb\\xbf)과 파일명 churn_history_날짜시각.csv 확인",
    },
    {
        "주차": "3주차",
        "시킨 일": "화면 2 — 버튼 블록 안에서 결과를 그려 다음 클릭에 사라지는 문제",
        "결과": "결과를 session_state['last']에 저장하고 if submitted 블록 밖에서 그림",
        "확인 방법": "AppTest로 제출 후 다른 버튼을 눌러도 점수·경고가 남는 것 확인",
    },
    {
        "주차": "3주차",
        "시킨 일": "화면 1 — 사이드바 필터가 지표·차트에 반영되는지 점검",
        "결과": "이미 충족. 코드 변경 없음",
        "확인 방법": "AppTest: 전체 7,043·26.5%·$64.8 / M2M 3,875·42.7% / 0~6개월 52.9% / 0명도 예외 없음",
    },
]

st.title("소개")

st.subheader("문제", divider="gray")
st.markdown(
    """
통신사는 떠난 고객을 뒤늦게 알게 된다. 이탈은 특정 집단에 쏠려 있는데도 전체 평균만 보고 있으면
어디에 손을 써야 할지 보이지 않는다. **누가 떠날 위험이 큰지 미리 알면** 쿠폰·상담 같은 적은 비용의
수단을 그 고객에게만 쓸 수 있다.
"""
)
c1, c2, c3 = st.columns(3)
c1.metric("전체 이탈률", "26.5%", help="7,043명 기준")
c2.metric("월 단위 계약", "42.7%", "+16.2%p", delta_color="inverse", help="3,875명 — 전체 평균의 1.6배")
c3.metric("가입 0~6개월", "52.9%", "+26.4%p", delta_color="inverse", help="1,481명 — 초기 이탈이 가장 심하다")
st.caption("화면 1의 필터로 직접 확인할 수 있는 값이다.")

st.subheader("사용자", divider="gray")
st.markdown(
    """
**통신사 고객관리팀 담당자.** 데이터 분석가가 아니라 매일 고객을 응대하는 실무자다.

- 상담 중에 고객 정보를 넣고 **지금 바로** 위험도를 알아야 한다 → 화면 2 (입력 폼 → 점수·근거)
- 점수만으로는 설명이 안 되니 **왜 위험한지 근거**가 필요하다 → `core.churn_score`가 reasons를 함께 돌려준다
- 어디에 쿠폰을 쓸지 정하려면 **전체 분포**를 봐야 한다 → 화면 1 (필터·차트)
"""
)
st.info("점수는 아직 규칙 기반 프로토타입이다. 2단계에서 학습한 ML 모델로 바뀌고, 화면 코드는 그대로 둔다.", icon=":material/science:")

st.subheader("데이터 출처", divider="gray")
st.markdown(
    """
**IBM Telco Customer Churn** — 통신사 고객 이탈 공개 데이터셋 (7,043행 × 21열, 이탈 26.5%).

| 항목 | 내용 |
|---|---|
| 공개 출처 | Kaggle `blastchar/telco-customer-churn` (IBM Cognos 샘플 데이터) |
| 서버 원본 | `~/work/shared/data/telco_churn.csv` (읽기 전용) |
| 이 프로젝트 사본 | `data/telco_churn.csv` — 경로는 `app.py` 폴더 기준 상대경로 |
| 열 목록 | `data/README.md` — 코드에서는 이 목록의 열 이름만 쓴다 |
| 정답 열 | `Churn` (Yes/No). 2단계 모델의 예측 대상 |
| 알려진 함정 | `TotalCharges`에 공백이 섞여 문자열로 읽힌다 → 화면 1의 `load()`에서 `pd.to_numeric(errors="coerce")` |

개인 식별 정보는 없다. `customerID`는 원본의 임의 발급 번호다.
"""
)

st.subheader("AI 활용 기록", divider="gray")
st.markdown("무엇을 시켰고, 받은 결과를 **어떻게 확인했는지** 남긴다. 확인하지 않은 결과는 기록하지 않는다.")
st.dataframe(pd.DataFrame(AI_LOG), width="stretch", hide_index=True)
st.caption(f"총 {len(AI_LOG)}건 · 작업 규칙은 프로젝트 루트의 CLAUDE.md에 적어 두고 AI가 매번 읽게 한다.")

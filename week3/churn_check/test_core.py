"""core.churn_score 테스트 — 4주차 '로직 + 테스트 2개' 예시. 실행: python -m pytest -q
Streamlit 없이 로직만 검증한다(core.py가 streamlit을 import하지 않는 이유)."""
from core import churn_score


def test_high_risk_month_to_month_new_customer():
    r = churn_score("Month-to-month", 3, 85.0, "Fiber optic", "No")
    assert r["score"] == 100 and r["level"] == "높음"          # 10+35+25+15+10+5 = 100 (상한)
    assert any("월 단위" in why for why in r["reasons"])


def test_low_risk_two_year_long_tenure():
    r = churn_score("Two year", 60, 30.0, "DSL", "Yes")
    assert r["score"] == 10 and r["level"] == "낮음" and r["reasons"] == []


def test_score_never_exceeds_100():
    r = churn_score("Month-to-month", 0, 120.0, "Fiber optic", "No")
    assert 0 <= r["score"] <= 100

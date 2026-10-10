"""이탈 위험 점수 — 지금은 '규칙 기반 가짜 백엔드'.
3단계(11~13주)에서 이 함수 호출을 REST API 호출(requests.post)로 바꾼다.
"""


def churn_score(contract: str, tenure: int, monthly: float, internet: str, support: str) -> dict:
    """규칙 기반 0~100 위험 점수. 근거(reasons)를 함께 돌려준다."""
    score, reasons = 10, []
    if contract == "Month-to-month":
        score += 35; reasons.append("월 단위 계약 (+35)")
    elif contract == "One year":
        score += 10; reasons.append("1년 계약 (+10)")
    if tenure < 6:
        score += 25; reasons.append("가입 6개월 미만 (+25)")
    elif tenure < 24:
        score += 10; reasons.append("가입 2년 미만 (+10)")
    if monthly >= 80:
        score += 15; reasons.append("월요금 80달러 이상 (+15)")
    if internet == "Fiber optic":
        score += 10; reasons.append("광랜 이용 (+10)")
    if support == "No":
        score += 5; reasons.append("기술지원 미가입 (+5)")
    score = min(score, 100)
    level = "높음" if score >= 60 else ("보통" if score >= 35 else "낮음")
    return {"score": score, "level": level, "reasons": reasons}

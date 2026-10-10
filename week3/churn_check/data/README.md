# data/telco_churn.csv — 열 목록 (IBM Telco Customer Churn)

7,043행 × 21열. 이탈률 26.5%. AI에게 코드를 시킬 때 **이 목록의 열 이름만** 쓰게 한다(`CLAUDE.md`에 참조).

| 열 | 뜻 | 타입 | 값 예 |
|---|---|---|---|
| `customerID` | 고객 ID | object | 7590-VHVEG, 5575-GNVDE, 3668-QPYBK … |
| `gender` | 성별 | object | Female, Male |
| `SeniorCitizen` | 고령자 여부(0/1) | int64 | 0, 1 |
| `Partner` | 배우자 유무 | object | Yes, No |
| `Dependents` | 부양가족 유무 | object | No, Yes |
| `tenure` | 가입 개월(0~72) | int64 | 0 ~ 72 |
| `PhoneService` | 전화 서비스 | object | No, Yes |
| `MultipleLines` | 복수 회선 | object | No phone service, No, Yes |
| `InternetService` | 인터넷 종류 | object | DSL, Fiber optic, No |
| `OnlineSecurity` | 온라인 보안 | object | No, Yes, No internet service |
| `OnlineBackup` | 온라인 백업 | object | Yes, No, No internet service |
| `DeviceProtection` | 기기 보호 | object | No, Yes, No internet service |
| `TechSupport` | 기술지원 | object | No, Yes, No internet service |
| `StreamingTV` | 스트리밍 TV | object | No, Yes, No internet service |
| `StreamingMovies` | 스트리밍 영화 | object | No, Yes, No internet service |
| `Contract` | 계약 유형 | object | Month-to-month, One year, Two year |
| `PaperlessBilling` | 전자 고지 | object | Yes, No |
| `PaymentMethod` | 결제 방법 | object | Electronic check, Mailed check, Bank transfer (automatic), Credit card (automatic) |
| `MonthlyCharges` | 월요금($) | float64 | 18.25 ~ 118.75 |
| `TotalCharges` | 누적 요금($, 문자열 → 숫자 변환 필요) | object | 29.85, 1889.5, 108.15 … |
| `Churn` | 이탈 여부(정답 열) | object | No, Yes |

- `TotalCharges`는 공백이 섞여 문자열로 읽힌다 → `pd.to_numeric(errors="coerce")` (화면 1의 `load()` 참고).
- 정답 열은 `Churn`(Yes/No). 2단계 모델의 예측 대상.
- 원본: `~/work/shared/data/telco_churn.csv` (읽기 전용) — 이 폴더의 사본을 쓴다.

# 이탈 위험 체크 서비스 (3주차 프로토타입)

## 실행 (학과 서버 JupyterHub · 내 계정 터미널)
```bash
cd ~/work/week3/churn_check     # ~/work 안의 내 프로젝트 폴더 (밖은 로그아웃 시 삭제)
python check_env.py             # 설정 파일(.streamlit/config.toml) 생성 · 내 앱 주소 출력 (1주차 스크립트)
pip install -r requirements.txt # 없는 패키지만 설치된다 (내 계정에 유지)
streamlit run app.py            # 이 터미널은 앱 전용 — 다른 명령은 새 터미널에서
```
브라우저에는 터미널의 `localhost:8501`이 아니라 **내 앱 주소**를 연다:
`https://ahnbi4.suwon.ac.kr:5300/user/<아이디>/proxy/8501/` (내 계정으로 로그인한 브라우저에서만 열린다).

## 구조
```
app.py                   홈
pages/1_데이터_탐색.py    데이터 로드(캐시)·필터·차트
pages/2_이탈_위험_체크.py 입력 폼 → core.churn_score → 결과·이력(session_state)
pages/3_소개.py          문제·사용자·데이터 출처·AI 활용 기록
core.py                  규칙 기반 점수 (3단계에서 REST API 호출로 교체)
test_core.py             로직 테스트 2개+ — python -m pytest -q  (4주차 "로직 + 테스트")
data/telco_churn.csv     샘플 데이터 (원본은 ~/work/shared/data/, 읽기 전용)
data/README.md           열 목록 — AI에게 열 이름을 지어내지 않게 CLAUDE.md에서 참조 (4주차)
check_env.py             1주차 점검 스크립트 사본 (이 폴더의 config.toml 생성·앱 주소 출력)
.gitignore               Git에 넣지 않을 것 (secrets.toml · env.txt · __pycache__ · app.log)
```

## 로컬 Git (LAB 3-6 · 이 폴더에서)
```bash
git init && git config user.name "홍길동" && git config user.email "22123456@suwon"
git add . && git commit -m "3화면 프로토타입"
```
`--global`은 쓰지 않는다 — `~/.gitconfig`는 `~/work` 밖이라 로그아웃하면 사라진다.

## 시연 준비 (5주차는 자기 자리 화면으로)
```bash
pkill -f "streamlit run"        # 남은 앱 종료 (내 계정 프로세스만 죽는다)
streamlit run app.py            # 재실행 — pages/ 파일을 추가했을 때도 재실행
# 3일 자동 로그아웃 뒤: 로그인 → 서버 시작 → 위 명령 다시 (파일은 ~/work에 그대로)
```
비밀값은 `.streamlit/secrets.toml`에 두고 코드에서는 `st.secrets["KEY"]`로 읽는다 (Git 제외, 공용 서버이므로 수업용 키만).

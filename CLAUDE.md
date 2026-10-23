# 프로젝트: 「줴줴이야」 롤 10분 승률 줄다리기 (Streamlit)

## 구조
- `app.py` 홈, `pages/` 화면, `core.py` 로직(**streamlit import 금지**), `data/` CSV, `shared.py` 화면 공용 캐시 로더
- 기능 명세는 `SPEC.md`, 기획서는 `docs/기획서_vN.md`(버전별로 새 파일, 이전 버전은 고치지 않는다)
- 경로는 `app.py` 기준 상대 경로. 열 이름은 `data/README.md`의 목록만 쓴다

## 코딩 규칙
- 밸런스 수치(계수·골드·경험·캡·쿨타임)는 **데이터에서 유도**한다. 새 상수를 지어내지 않는다 (설계값은 `N타`·`SEC` 둘뿐)
- `core.win_rate()` 반환 형식 `{"score": int, "level": str, "reasons": list[str]}`은 고정 (3단계 API)
- 새 패키지는 설치하기 전에 먼저 물어볼 것 (설치하면 `requirements.txt`에도 추가)
- 빈 결과·잘못된 입력에서 오류 대신 안내(`st.warning`/`st.toast`)

## 하지 말 것
- 요청한 파일 외 수정, 전체 재작성, 비밀값 하드코딩
- `env.txt`·`log/`(대화 기록에 비밀번호가 들어 있다)를 커밋하거나 읽어서 출력하지 않는다
- 커밋·푸시는 사용자가 요청할 때만. 대상 저장소는 `github.com/poik1118/usw-ml_project` (공개)
- 이 폴더(`~/work/gg_battle`) 밖의 파일 수정, `rm -rf` / `sudo`

## 검증
- `core.py` 수정 시 `python -m pytest -q` (51 passed 기준)
- 밸런스 수치를 바꾸면 `python bot_test.py 200`
- 화면 수정 후 앱을 8611로 띄워 `python browser_test.py` — 경기 중 **값이 갱신되는지**까지 눈으로 확인한다

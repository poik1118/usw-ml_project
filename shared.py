"""화면들이 공유하는 streamlit 헬퍼. 로직은 전부 core.py에 있다."""

import hashlib
import pickle
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

import core

HERE = Path(__file__).parent
DATA = HERE / "data" / "high_diamond_ranked_10min.csv"
CACHE = HERE / "runtime" / "engine.pkl"


@st.cache_data
def load_data() -> pd.DataFrame:
    """경로 기반 로드만 캐시한다."""
    return pd.read_csv(DATA)


def _cache_key() -> str:
    """데이터 파일이나 core.py가 바뀌면 캐시를 버리게 하는 지문.

    설정값을 골라 넣으면 빠뜨린 것(스폰 시각·학습 코드·Engine 필드)이 옛 캐시로 조용히 남는다
    → core.py 내용 전체를 지문에 넣는다.
    """
    stat = DATA.stat()
    h = hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}:".encode())
    h.update(Path(core.__file__).read_bytes())
    return h.hexdigest()[:16]


@st.cache_resource(show_spinner=False)
def get_engine() -> core.Engine:
    """승률 엔진. 프로세스 안에서는 cache_resource가, 재시작 사이에는 디스크가 캐시한다.

    학습은 3.3초 걸리는데 Engine은 822바이트로 직렬화된다. 디스크에 두면 서버를
    다시 켜도 즉시 뜬다 — 안 그러면 첫 로드 때 화면이 **9초 동안 반쯤 그려진 채**
    남아서 "테마가 깨졌다"처럼 보인다 (실측 확인).
    """
    key = _cache_key()
    cached = _read_cache(key)
    if cached is not None:
        return cached
    with st.spinner("승률 모델 학습 중… (최초 1회, 약 3초)"):
        engine = core.fit_engine(load_data())
    _write_cache(key, engine)
    return engine


def _read_cache(key: str) -> core.Engine | None:
    try:
        blob = pickle.loads(CACHE.read_bytes())
        return blob["engine"] if blob.get("key") == key else None
    except Exception:
        return None          # 캐시는 있으면 좋고 없으면 그만이다


def _write_cache(key: str, engine: core.Engine) -> None:
    try:
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_bytes(pickle.dumps({"key": key, "engine": engine}))
    except OSError:
        pass


def engine_or_stop() -> core.Engine:
    if not DATA.exists():
        st.error(f"데이터가 없습니다: `{DATA.relative_to(HERE)}` — README의 다운로드 명령을 실행하세요.")
        st.stop()
    return get_engine()


def fmt_plan(seq) -> str:
    """순서 리스트를 '명령 N타(완성 M개)'로 요약한다.

    `suggest_sequence()`는 **타수** 목록을 돌려준다. N타가 1이 아닌 명령
    (level 3타 · dragon 4타 · tower 5타 …)은 타수와 완성 개수가 다르므로
    둘 다 표시한다 — `dragon 4타`는 드래곤 4마리가 아니라 **1마리**다.
    """
    if not seq:
        return "(없음)"
    parts = []
    for cmd, k in Counter(seq).items():
        n = core.COMMANDS[cmd]["n"]
        parts.append(f"{cmd} {k}타" + (f"(={k // n}개)" if n > 1 else ""))
    return " · ".join(parts)


def level_color(score: int) -> str:
    """색은 core.LEVELS의 등급에서 고른다 — 기준 점수를 두 곳에 적으면 라벨과 색이 어긋난다."""
    name = next((n for cut, n in core.LEVELS if score >= cut), None)
    return {"유리": "green", "약간 유리": "blue", "박빙": "orange"}.get(name, "red")

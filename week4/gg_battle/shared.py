"""화면들이 공유하는 streamlit 헬퍼. 로직은 전부 core.py에 있다."""

import hashlib
import pickle
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
    """데이터 파일과 밸런스 설정이 바뀌면 캐시를 버리게 하는 지문."""
    stat = DATA.stat()
    cfg = repr((core.FEATURES, core.SEC, core.COMPRESS, core.LEVEL_START,
                {c: (s["n"], s["contested"]) for c, s in core.COMMANDS.items()}))
    return hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}:{cfg}".encode()).hexdigest()[:16]


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
    counts: dict[str, int] = dict(seq) if isinstance(seq, dict) else {}
    if not counts:
        for cmd in seq:
            counts[cmd] = counts.get(cmd, 0) + 1
    parts = []
    for cmd, k in counts.items():
        n = core.COMMANDS[cmd]["n"]
        parts.append(f"{cmd} {k}타" + (f"(={k // n}개)" if n > 1 else ""))
    return " · ".join(parts)


def level_color(score: int) -> str:
    if score >= 70:
        return "green"
    if score >= 55:
        return "blue"
    if score >= 45:
        return "orange"
    return "red"

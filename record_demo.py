"""백업 영상 자동 녹화 — SPEC.md 6절 시연 시나리오 + 1대1 대결(두 화면 나란히).

실행 (browser_test.py와 같은 준비 · 앱을 8611 포트로 띄운 뒤):
    python record_demo.py        → log/demo_main.mp4 · log/demo_battle.mp4  (log/는 .gitignore)

화면 조작은 전부 SPEC.md의 고정 입력값이고, 기대값이 화면에 안 보이면 녹화를 실패로 끝낸다
— "녹화는 됐는데 엉뚱한 화면"인 백업 영상을 시연 당일에 처음 발견하지 않으려고.
"""

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_test import BASE, exceptions, start_invite, tap, wait_ready

OUT = Path(__file__).resolve().parent / "log"
HD = {"width": 1280, "height": 720}
READ = 4000          # 기대값이 뜬 뒤 시청자가 읽는 시간(ms)


def encode(inputs: list[str], mp4: Path) -> None:
    """ffmpeg 입력 인자 → LMS 제출용 mp4(H.264). 입력이 2개면 좌우로 붙인다."""
    n = inputs.count("-i")
    args = ["ffmpeg", "-y", "-loglevel", "error", *inputs]
    if n > 1:
        args += ["-filter_complex", f"hstack=inputs={n}:shortest=1"]
    subprocess.run(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                           str(mp4)], check=True)


def expect(where, text: str) -> None:
    """기대값이 화면에 보일 때까지 기다렸다가 READ만큼 보여준다. 안 보이면 예외 — 잘못 찍힌 영상을 남기지 않는다."""
    where.get_by_text(text).first.wait_for(timeout=20000)
    where.wait_for_timeout(READ)


def go(page, name: str) -> None:
    page.locator('[data-testid="stSidebarNav"] a', has_text=name).first.click()
    page.wait_for_timeout(2000)


def set_slider(page, label: str, steps: int, target: str) -> None:
    """사이드바 select_slider를 왼쪽(Blue 쪽)으로 steps칸 옮긴다. 옵션이 +cap…−cap 순이다.

    streamlit 1.65의 슬라이더는 native range(값 = 옵션 인덱스)다. 한 칸씩 누르면 칸마다 재실행돼
    화면이 15초간 회색으로 남는다 → 목표 한 칸 앞까지 값을 바로 넣고, 마지막 한 칸만 키보드로 확정한다.
    """
    thumb = page.locator('[data-testid="stSidebar"] [data-testid="stSlider"]',
                         has_text=label).first.get_by_role("slider")
    thumb.scroll_into_view_if_needed()
    thumb.evaluate("""(e, v) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, v);
        e.dispatchEvent(new Event('input', {bubbles: true}));
    }""", str(int(thumb.input_value()) - steps + 1))
    thumb.press("ArrowLeft")
    page.wait_for_function("([e, t]) => e.getAttribute('aria-valuetext') === t",
                           arg=[thumb.element_handle(), target], timeout=10000)


def main_demo(browser, tmp: Path) -> None:
    ctx = browser.new_context(viewport=HD, record_video_dir=tmp / "main", record_video_size=HD)
    page = ctx.new_page()
    born = time.monotonic()
    page.goto(BASE + "/", wait_until="domcontentloaded")
    wait_ready(page, 3000)
    skip = time.monotonic() - born - 0.5

    # 0. 홈 — 문제·대상·Must 3개
    expect(page, "Must 3개")
    page.wait_for_timeout(3000)

    # 1. 승률 분해 (US-1)
    go(page, "시뮬레이터")
    page.get_by_role("tab", name="상태 슬라이더").click()
    for label, steps, target, shown in (("골드", 30, "Blue +1,500", "Blue 67%"),    # 50골드 눈금
                                        ("dragon", 1, "Blue +1", "Blue 74%"),
                                        ("tower", 1, "Blue +1", "Blue 68%")):
        set_slider(page, label, steps, target)
        expect(page, shown)
    expect(page, "타워 차 (-0.275 logit, -5.7%p)")

    # 2. 데이터 근거 (US-2)
    go(page, "데이터 탐색")
    page.get_by_role("tab", name="계수 부호").click()
    page.get_by_text("단독 상관은 양수인데 계수는 음수").first.scroll_into_view_if_needed()
    expect(page, "towerDiff")
    page.get_by_role("tab", name="골드 통제 비교").click()
    page.get_by_text("킬 +3 이상 & 골드 뒤짐").first.scroll_into_view_if_needed()
    expect(page, "35.3%")

    # 3. 시뮬레이터 단독 모드 (US-4) — 타자 속도는 기본값 300
    go(page, "시뮬레이터")
    page.get_by_role("tab", name="전략 시나리오").click()
    for strat, shown in (("킬사이클", "96%"), ("타워러시", "91%"), ("시야전략", "51%")):
        page.get_by_test_id("stSelectbox").first.click()
        page.get_by_role("option", name=strat, exact=True).click()
        expect(page, shown)

    errs = exceptions(page)
    assert not errs, errs
    video = Path(page.video.path())
    ctx.close()                                    # 닫아야 webm이 디스크에 끝까지 써진다
    encode(["-ss", f"{skip:.2f}", "-i", str(video)], OUT / "demo_main.mp4")    # 앞의 로딩 구간을 자른다


def battle_demo(browsers: list, tmp: Path) -> None:
    """P1·P2를 별도 브라우저 프로세스(실제 기기 2대와 같은 조건)로 띄우고, **스크린샷을 이어 붙여** 좌우 영상을 만든다.

    playwright 영상 녹화(screencast)를 켜면 1초 자동 갱신 화면이 수십 초씩 멈췄다. 녹화 없이 같은 조작을
    재면 양쪽 모두 1초마다 갱신되고, 변경 전 코드도 녹화하면 똑같이 멈췄다(측정) — 앱이 아니라 녹화 방식 문제다.
    """
    frames = tmp / "frames"
    frames.mkdir()
    pages = [b.new_page(viewport={"width": 800, "height": 900}) for b in browsers]
    p1, p2 = pages
    for pg in pages:
        pg.goto(BASE + "/1대1_대결", wait_until="domcontentloaded")
        wait_ready(pg, 3000)
    try:
        tap(p1, "방 비우기", timeout=3000)  # 직전 경기(browser_test 등)의 결과 화면으로 영상이 시작되지 않게
        p1.wait_for_timeout(3000)
    except Exception:
        pass                             # 이미 빈 방
    shots, began = 0, time.monotonic()

    def hold(ms: int) -> None:
        """ms 동안 양쪽 화면을 같은 번호로 계속 찍는다 (영상의 한 프레임 = 두 화면의 같은 순간)."""
        nonlocal shots
        end = time.monotonic() + ms / 1000
        while True:
            for k, pg in enumerate(pages):
                pg.screenshot(path=frames / f"{k}_{shots:05d}.png")
            shots += 1
            if time.monotonic() >= end:
                return

    p2.get_by_text("P2", exact=True).first.click()
    hold(2000)
    start_invite(p1)                     # 방이 비었으면 '대결 신청', 직전 경기가 남았으면 '다시 대결'
    hold(2000)
    tap(p1, "수락")
    hold(1500)
    tap(p2, "수락")
    hold(4000)                           # COUNTDOWN 3초

    def chat(text: str) -> None:
        box = p2.locator('[data-testid="stChatInputTextArea"]')
        box.click()                      # 포커스 없이 fill하면 React가 값을 못 받는다
        box.fill(text)
        box.press("Enter")

    def p1_plan(t: float) -> str:        # 탭 버튼: 레벨 → 타워 → 드래곤 경합 → 골드 → 전령 경합
        return ("level ×3" if t < 12 else "tower ×5" if t < 30 else "dragon ×4" if t < 40
                else "herald ×2" if t >= 48 else "gold")

    def p2_plan(t: float) -> str:        # 채팅: 킬(쿨타임 9.7초)·골드 → 드래곤·전령 경합
        return ("dragon" if 30 <= t < 40 else "herald" if t >= 48
                else "kill" if int(t) % 4 == 0 else "gold")

    def left(pg) -> str:
        try:
            return pg.locator('[data-testid="stMetric"]', has_text="남은 시간").first.locator(
                '[data-testid="stMetricValue"]').inner_text(timeout=400)
        except Exception:
            return "?"

    # 실시간 영역이 멈춘 영상은 버린다 (영상 녹화 방식에서 실제로 있었다)
    seen = {pg: ("", time.monotonic()) for pg in pages}
    stalled = 0.0
    chat("baron")                        # 예외 입력 — 토스트 '없는 명령어: baron'
    start = time.monotonic()
    while (t := time.monotonic() - start) < 58:
        for pg in pages:
            v, since = seen[pg]
            if (now := left(pg)) != v:
                seen[pg] = (now, time.monotonic())
            else:
                stalled = max(stalled, time.monotonic() - since)
        try:
            tap(p1, p1_plan(t), timeout=2000)
        except Exception:
            pass                         # 쿨타임·캡·선점으로 막힌 순간 — 실제 플레이어처럼 다음 입력으로
        try:
            chat(p2_plan(t))
        except Exception:
            pass
        hold(700)
    for pg in pages:
        pg.get_by_text(re.compile("P1 승리|P2 승리|무승부")).first.wait_for(timeout=20000)
        pg.get_by_text("스코어보드").first.scroll_into_view_if_needed()
    hold(8000)

    errs = exceptions(p1) + exceptions(p2)
    assert not errs, errs
    assert stalled < 5, f"실시간 영역이 {stalled:.0f}초 멈췄다 — 다시 실행"
    # shortcut: 프레임 간격을 평균 fps로 본다 — 입력 처리 중엔 간격이 벌어져 그 구간이 약간 빨리 감긴다
    fps = f"{shots / (time.monotonic() - began):.3f}"
    encode([a for k in (0, 1) for a in ("-framerate", fps, "-i", str(frames / f"{k}_%05d.png"))],
           OUT / "demo_battle.mp4")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        b, b2 = (pw.chromium.launch(args=["--no-sandbox"]) for _ in range(2))
        main_demo(b, Path(tmp))
        print("✅ log/demo_main.mp4")
        battle_demo([b, b2], Path(tmp))
        print("✅ log/demo_battle.mp4")
        b.close()
        b2.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

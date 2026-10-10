"""브라우저 자동 테스트 — 4개 화면 로드 + 2세션 동시 대결 + 모바일 뷰포트.

사전 준비 (한 번만, ~/work 안에 설치되어 로그아웃 후에도 유지된다):
    npx -y playwright@latest install chromium        # PLAYWRIGHT_BROWSERS_PATH 지정하고
    mamba create -y -p ~/work/.chromedeps nspr nss atk-1.0 at-spi2-atk at-spi2-core \
        xorg-libxcomposite xorg-libxdamage -c conda-forge
    pip install --user playwright

실행:
    streamlit run app.py --server.port 8601 &        # 다른 터미널에서
    export PLAYWRIGHT_BROWSERS_PATH=~/work/.playwright-browsers
    export PLAYWRIGHT_NODEJS_PATH=/usr/bin/node      # 번들 node가 이 서버에선 안 돈다
    export LD_LIBRARY_PATH=~/work/.chromedeps/lib:$LD_LIBRARY_PATH
    python browser_test.py
"""

import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8611"
PAGES = ["/", "/데이터_탐색", "/시뮬레이터", "/1대1_대결"]


def exceptions(page) -> list[str]:
    return [(el.inner_text() or "")[:300]
            for el in page.query_selector_all('[data-testid="stException"]')]


def wait_ready(page, ms: int = 5000) -> None:
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=30000)
    page.wait_for_timeout(ms)


def tap(page, name: str, timeout: int = 15000) -> None:
    """버튼을 눌러준다. 스크롤부터 한다 — 바로 click하면 화면 밖일 때 타임아웃난다."""
    b = page.get_by_role("button", name=name)
    b.scroll_into_view_if_needed(timeout=timeout)
    b.click(timeout=timeout)


def start_invite(page) -> None:
    """방이 비어 있으면 '대결 신청', 직전 경기가 남아 있으면 '다시 대결'을 누른다."""
    for name in ("대결 신청", "다시 대결"):
        try:
            tap(page, name, timeout=4000)
            return
        except Exception:
            continue
    raise AssertionError("신청 버튼을 찾지 못했다")


def main() -> int:
    ok = True
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox"])

        print("1. 화면 로드")
        for path in PAGES:
            pg = b.new_page()
            pg.goto(BASE + path, wait_until="domcontentloaded")
            wait_ready(pg, 6000)
            errs = exceptions(pg)
            print(f"   {path:<14} {'✅' if not errs else '❌ ' + errs[0]}")
            ok &= not errs
            pg.close()

        print("\n2. 2세션 동시 대결 (P1 탭 버튼 / P2 채팅 입력)")
        p1, p2 = b.new_page(), b.new_page()
        for pg in (p1, p2):
            pg.goto(BASE + "/1대1_대결", wait_until="domcontentloaded")
            wait_ready(pg)
        p2.get_by_text("P2", exact=True).first.click()
        p2.wait_for_timeout(3000)
        # 롤 매칭 수락 흐름: 신청 → 양쪽 수락 → 카운트다운 → 시작
        start_invite(p1)
        time.sleep(3)
        tap(p1, "수락")
        time.sleep(2)
        tap(p2, "수락")
        time.sleep(7)        # COUNTDOWN 3초 + 전환

        taps = types = 0
        last_err = ""
        t0 = time.time()
        while time.time() - t0 < 20:
            try:
                tap(p1, "tower ×5", timeout=2500)
                taps += 1
            except Exception:
                pass
            try:
                ta = (p2.query_selector('[data-testid="stChatInputTextArea"]')
                      or p2.query_selector("textarea"))
                if ta:
                    ta.click()          # 포커스 없이 fill하면 React가 값을 못 받는다
                    ta.fill("gold")
                    ta.press("Enter")
                    types += 1
            except Exception as e:
                last_err = str(e)[:120]
            time.sleep(0.9)
        p1.wait_for_timeout(2500)
        body = p1.inner_text("body")
        errs = exceptions(p1) + exceptions(p2)
        print(f"   P1 탭 {taps}회 / P2 채팅 {types}회" + (f"  (마지막 오류: {last_err})" if last_err else ""))
        ok &= taps > 0 and types > 0
        for key in ("남은 시간", "큐", "골드"):
            print(f"   {'✅' if key in body else '❌'} '{key}' 표시")
            ok &= key in body
        print(f"   {'✅ 예외 없음' if not errs else '❌ 예외 ' + str(len(errs))}")
        ok &= not errs
        p1.close()
        p2.close()        # run_every fragment가 계속 도므로 반드시 닫는다

        print("\n3. 모바일 뷰포트 390×844")
        m = b.new_page(viewport={"width": 390, "height": 844})
        m.goto(BASE + "/1대1_대결", wait_until="domcontentloaded")
        wait_ready(m)
        # 탭 버튼은 게임 중에만 보인다 — 신청·수락을 거쳐 시작시킨다
        start_invite(m)
        time.sleep(2.5)
        tap(m, "수락")
        time.sleep(2)
        import json as _j, pathlib as _p, time as _t
        rt = _p.Path(__file__).parent / "runtime"
        inv = _j.loads((rt / "room.json").read_text())["invite"]
        other = "accept_P2.json" if "P2" not in m.inner_text("body") else "accept_P2.json"
        (rt / other).write_text(_j.dumps({"invite": inv, "at": _t.time()}))
        time.sleep(6)
        overflow = m.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        labels = [(x.inner_text() or "").strip() for x in m.query_selector_all("button")]
        cmds = [x for x in labels if x.split(" ")[0] in __import__("core").COMMANDS]
        print(f"   가로 넘침 {overflow}px {'✅' if overflow <= 8 else '❌'}")
        print(f"   명령어 탭 버튼 {len(cmds)}개 {'✅' if len(cmds) >= 11 else '❌'}")
        errs = exceptions(m)
        print(f"   {'✅ 예외 없음' if not errs else '❌ 예외 ' + str(len(errs))}")
        ok &= overflow <= 8 and len(cmds) >= 11 and not errs
        b.close()

    print("\n" + ("✅ 전부 통과" if ok else "❌ 문제 있음"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

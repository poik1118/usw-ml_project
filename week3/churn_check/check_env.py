"""LAB 1-4 · 서버 개발환경 점검 스크립트 — 실행: python check_env.py
1주차 목표: 아래 항목이 전부 OK 이면 2주차 실습을 시작할 수 있다.

이 과목의 개발환경은 학과 서버 JupyterHub(https://ahnbi4.suwon.ac.kr:5300/)의 내 계정(수업코드+학번)이다.
- 모든 작업 파일은 ~/work 안에 둔다 (그 밖은 로그아웃하면 삭제된다)
- 패키지가 없으면 내 계정에 pip install 하면 되고, 설치한 것은 유지된다
- Streamlit 앱은 내 서버 안의 8501 포트로 띄우고, 브라우저에서는 JupyterHub가 대신 열어 주는
  "내 앱 주소" https://ahnbi4.suwon.ac.kr:5300/user/<아이디>/proxy/8501/ 로 본다 (이 스크립트가 출력)
- 이 스크립트는 .streamlit/config.toml 을 만들어 주므로 학생은 streamlit run 만 치면 된다
"""
import importlib
import importlib.util
import os
import platform
import re
import shutil
import socket
import subprocess
import sys

MIN_PY = (3, 10)
PACKAGES = ["streamlit", "pandas", "numpy"]      # 2~3주차 실습에 필요한 최소 패키지
HUB = "https://ahnbi4.suwon.ac.kr:5300"          # JupyterHub 주소 (수업 안내문 기준)
PORT = 8501                                      # 내 서버 안의 Streamlit 포트 (계정마다 별도 서버라 전원 같은 번호)
WORK = os.path.expanduser("~/work")              # 유일하게 남는 작업 폴더
SHARED = [os.path.join(WORK, "shared"), os.path.join(WORK, "shared_all")]

rows = []   # (항목, 상태, 비고)


def ok(name, note=""):
    rows.append((name, "OK", note))


def fail(name, note=""):
    rows.append((name, "확인 필요", note))


def warn(name, note=""):
    rows.append((name, "주의", note))


def short(path):
    """홈 아래 경로는 ~/… 로 줄여 보여 준다"""
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


# 1) 파이썬 버전
v = sys.version_info
(ok if v >= MIN_PY else fail)("Python %d.%d.%d" % v[:3],
                             "3.10 이상 필요" if v < MIN_PY else platform.python_implementation())

# 2) 패키지 — 없으면 내 계정에 설치 (유지된다)
for name in PACKAGES:
    try:
        m = importlib.import_module(name)
        ok(f"패키지 {name}", getattr(m, "__version__", ""))
    except ImportError:
        fail(f"패키지 {name}", f"터미널에서  pip install {name}  후 다시 실행 (내 계정에만 설치되고 유지된다)")

# 3) Claude Code (터미널에서 claude 로 실행)
claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
if os.path.exists(claude):
    try:
        out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        ok("도구 claude", out or claude)
    except Exception:
        ok("도구 claude", claude)
else:
    fail("도구 claude", "터미널에서 claude 를 쳐서 실행되는지 확인 — 안 되면 강사에게")

# 4) 작업 폴더 — ~/work 안인가 (밖이면 로그아웃 시 삭제)
cwd = os.getcwd()
in_work = os.path.realpath(cwd).startswith(os.path.realpath(WORK)) if os.path.isdir(WORK) else False
if in_work:
    ok("작업 폴더", f"{short(cwd)}  (~/work 안 — 로그아웃 후에도 유지)")
elif os.path.isdir(WORK):
    fail("작업 폴더", f"현재 위치 {short(cwd)} 는 ~/work 밖 — 로그아웃하면 삭제된다. cd ~/work/… 후 다시 실행")
else:
    fail("작업 폴더", "~/work 폴더가 없다 — 학과 서버 계정이 아닌 곳에서 실행 중? 강사에게")

# 5) 공유 폴더 (읽기 전용) 존재 확인
found = [short(p) for p in SHARED if os.path.isdir(p)]
(ok if found else warn)("공유 폴더", " · ".join(found) if found else "~/work/shared 가 보이지 않음 — 강사 게시 전이거나 다른 계정")

# 6) 내 앱 주소 — JupyterHub 가 내 서버의 8501 포트를 대신 열어 주는 경로
prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")          # 예: /user/262mb22123456/
user = os.environ.get("JUPYTERHUB_USER")
if not prefix and user:
    prefix = f"/user/{user}/"
if prefix:
    app_url = f"{HUB}{prefix}proxy/{PORT}/"
    ok("내 앱 주소", app_url)
    if importlib.util.find_spec("jupyter_server_proxy") is None:
        warn("프록시 확장", "jupyter-server-proxy 가 이 파이썬에 없음 — 앱 주소가 안 열리면 강사에게 (설치·서버 재시작 필요)")
else:
    app_url = f"http://localhost:{PORT}"
    warn("내 앱 주소", f"JupyterHub 환경이 아님 — 내 컴퓨터라면 {app_url} 로 연다")

# 7) .streamlit/config.toml — 포트·프록시 호환 설정 자동 생성 (있으면 포트만 확인)
cfg_dir = os.path.join(cwd, ".streamlit")
cfg = os.path.join(cfg_dir, "config.toml")
wanted = (f"[server]\nport = {PORT}\naddress = \"0.0.0.0\"\nheadless = true\n"
          "enableCORS = false\nenableXsrfProtection = false\n\n"
          "[browser]\ngatherUsageStats = false\n")
if os.path.exists(cfg):
    txt = open(cfg, encoding="utf-8").read()
    if re.search(rf"^\s*port\s*=\s*{PORT}\s*$", txt, re.M):
        ok("설정 .streamlit/config.toml", f"port = {PORT}")
    else:
        warn("설정 .streamlit/config.toml", f"port 가 {PORT} 이 아님 — 파일을 지우고 다시 실행하면 재생성")
else:
    os.makedirs(cfg_dir, exist_ok=True)
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(wanted)
    ok("설정 .streamlit/config.toml", f"새로 생성 (port = {PORT}) — 이제 streamlit run 만 치면 된다")

# 8) 포트가 이미 사용 중인가 (내 서버 안이라 사용 중이면 내 이전 앱이다)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("0.0.0.0", PORT))
    ok("포트 비어 있음", f"{PORT}")
except OSError:
    warn("포트 사용 중", f"{PORT} 에 이미 내 앱이 떠 있음 — 그 터미널에서 Ctrl+C, 또는  pkill -f \"streamlit run\"")
finally:
    s.close()

# 9) 출력
def dw(txt):                      # 한글은 2칸 폭
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in txt)


def pad(txt, width):
    return txt + " " * max(0, width - dw(txt))


w = max(dw(r[0]) for r in rows) + 2
who = f"JupyterHub · {user}" if user else platform.node()
print("=" * 64)
print(" 서버 개발환경 점검 결과  (" + who + ")")
print("=" * 64)
for name, status, note in rows:
    print(f"{pad(name, w)} {pad(status, 11)} {note}")
print("-" * 64)
bad = [r for r in rows if r[1] == "확인 필요"]
if bad:
    print(f"확인 필요 {len(bad)}건 — 비고를 따라 조치한 뒤 python check_env.py 를 다시 실행하세요.")
    sys.exit(1)
print("모두 준비되었습니다. 다음: streamlit run hello_streamlit.py  →  브라우저 새 탭에 " + app_url)

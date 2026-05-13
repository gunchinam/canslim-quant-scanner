# -*- coding: utf-8 -*-
"""
종목스캐너 스크린샷 캡처 (스캔 결과 포함)
1. 앱 실행
2. 첫 번째 섹터 선택 후 SCAN
3. 결과 로드 완료 대기
4. 각 전략/시장 전환하며 캡처
"""
import subprocess, sys, os, time
import win32gui, win32con, win32ui
import pyautogui
from PIL import Image
from ctypes import windll

ROOT = r"C:\Users\new123\Documents\카카오톡 받은 파일\종목스캐너"
OUT  = os.path.join(ROOT, "screenshots")
os.makedirs(OUT, exist_ok=True)
os.chdir(ROOT)
pyautogui.FAILSAFE = False

# ── 앱 실행 ───────────────────────────────────────────
print("앱 시작 중...")
proc = subprocess.Popen([sys.executable, "quant_nexus_v20.py"])
print("로딩 대기 (22초)...")
time.sleep(22)

# ── 창 찾기 ───────────────────────────────────────────
hwnd = None
def _cb(h, _):
    global hwnd
    if win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        if "스캐너" in t or "(.)(.)" in t:
            hwnd = h
win32gui.EnumWindows(_cb, None)

if not hwnd:
    print("ERROR: 창을 찾지 못했습니다.")
    proc.terminate()
    sys.exit(1)

print(f"창 발견: hwnd={hwnd}")
win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
time.sleep(0.5)
win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
time.sleep(1.5)

wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
print(f"창 크기: {wr-wl}x{wb-wt}")

# ── PrintWindow 캡처 ──────────────────────────────────
def pw_capture():
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = r - l, b - t
    hdc = win32gui.GetWindowDC(hwnd)
    mdc = win32ui.CreateDCFromHandle(hdc)
    sdc = mdc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mdc, w, h)
    sdc.SelectObject(bmp)
    if not windll.user32.PrintWindow(hwnd, sdc.GetSafeHdc(), 2):
        windll.user32.PrintWindow(hwnd, sdc.GetSafeHdc(), 0)
    info = bmp.GetInfo()
    bits = bmp.GetBitmapBits(True)
    img  = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']),
                            bits, 'raw', 'BGRX', 0, 1)
    win32gui.DeleteObject(bmp.GetHandle())
    sdc.DeleteDC(); mdc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)
    return img

def capture(name, note=""):
    time.sleep(0.8)
    img  = pw_capture()
    path = os.path.join(OUT, f"{name}.png")
    img.save(path)
    kb = os.path.getsize(path) // 1024
    print(f"  [OK] {name}.png  ({kb} KB)  {note}")
    return img

def crop_save(img, name, x1p, y1p, x2p, y2p):
    W, H = img.size
    cr   = img.crop((int(W*x1p), int(H*y1p), int(W*x2p), int(H*y2p)))
    path = os.path.join(OUT, f"{name}.png")
    cr.save(path)
    kb = os.path.getsize(path) // 1024
    print(f"  [OK] {name}.png  ({kb} KB)  [crop]")

# ── 버튼 찾기 (x좌표 순) ─────────────────────────────
# 헤더 버튼: [MOM(0) BAL(1) VAL(2) CAN(3) SCA(4)] [US(5) KR(6) EU(7)]
def get_header_buttons():
    btns = []
    def cb(h, _):
        if win32gui.GetClassName(h) == "Button":
            r = win32gui.GetWindowRect(h)
            if r[1] < wt + 75:
                btns.append((r[0], h))
    win32gui.EnumChildWindows(hwnd, cb, None)
    btns.sort()
    return [h for _, h in btns]

# 사이드바 버튼: y 순 [SCAN(0) SCAN ALL(1) STOP(2) ...]
def get_sidebar_buttons():
    btns = []
    def cb(h, _):
        if win32gui.GetClassName(h) == "Button":
            r = win32gui.GetWindowRect(h)
            if r[1] >= wt + 75 and r[0] < wl + 280:
                btns.append((r[1], h))
    win32gui.EnumChildWindows(hwnd, cb, None)
    btns.sort()
    return [h for _, h in btns]

def click_btn(bh):
    r  = win32gui.GetWindowRect(bh)
    cx = (r[0] + r[2]) // 2
    cy = (r[1] + r[3]) // 2
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.2)
    pyautogui.click(cx, cy)
    time.sleep(0.6)

header_btns  = get_header_buttons()
sidebar_btns = get_sidebar_buttons()
print(f"\n헤더 버튼: {len(header_btns)}개, 사이드바 버튼: {len(sidebar_btns)}개")

IDX = {"MOM":0, "BAL":1, "VAL":2, "CAN":3, "SCA":4, "US":5, "KR":6, "EU":7}

def click_named(name):
    idx = IDX.get(name)
    if idx is None or idx >= len(header_btns):
        print(f"  [!] {name} 버튼 없음")
        return False
    click_btn(header_btns[idx])
    return True

# ── 첫 섹터 클릭 후 SCAN ──────────────────────────────
# 사이드바 섹터 트리뷰의 첫 번째 항목 클릭 (상단 ~175px 위치)
sector_x = wl + 143
sector_y  = wt + 175
print(f"\n섹터 클릭: ({sector_x}, {sector_y})")
try:
    win32gui.SetForegroundWindow(hwnd)
except Exception:
    pass
time.sleep(0.3)
pyautogui.click(sector_x, sector_y)
time.sleep(0.8)

# SCAN 버튼 클릭 (사이드바 첫 번째 버튼)
if sidebar_btns:
    print("SCAN 버튼 클릭...")
    click_btn(sidebar_btns[0])
    print("스캔 실행 중 - 결과 대기 (90초)...")
    # 30초마다 경과 출력
    for i in range(3):
        time.sleep(30)
        print(f"  ... {(i+1)*30}초 경과")
else:
    print("[!] SCAN 버튼 못 찾음. 빈 화면으로 계속 진행")

# ── 스캔 완료 후 캡처 ─────────────────────────────────
print("\n캡처 시작!")

# 01 스캔 결과 전체
img = capture("01_스캔결과_BALANCED", "US + BALANCED 스캔 결과")
if img:
    crop_save(img, "02_헤더_버튼", 0, 0, 1.0, 0.09)
    crop_save(img, "03_사이드바", 0, 0.08, 0.18, 1.0)
    crop_save(img, "04_결과테이블", 0.18, 0.08, 1.0, 0.88)

# 전략 전환 (같은 데이터, 점수 재산출)
for strat, lbl, note in [
    ("MOM", "05_전략_MOMENTUM",  "모멘텀 전략으로 재산출"),
    ("CAN", "06_전략_CANSLIM",   "CAN SLIM 전략"),
    ("SCA", "07_전략_SCALPING",  "단타 스캐닝 뷰"),
    ("VAL", "08_전략_VALUE",     "가치 전략"),
    ("BAL", "09_전략_BALANCED",  "균형 전략 복귀"),
]:
    if click_named(strat):
        capture(lbl, note)

# 시장 전환 (KR - 섹터 목록만 보여도 됨)
click_named("KR")
capture("10_KR시장_섹터목록", "한국 시장 섹터 목록")

click_named("EU")
capture("11_EU시장_섹터목록", "유럽 시장 섹터 목록")

click_named("US")

# ── 결과 ──────────────────────────────────────────────
files = sorted(f for f in os.listdir(OUT) if f.endswith(".png"))
print(f"\n[완료] {len(files)}개 -> {OUT}")
for f in files:
    kb = os.path.getsize(os.path.join(OUT, f)) // 1024
    print(f"   {f}  ({kb} KB)")

proc.terminate()

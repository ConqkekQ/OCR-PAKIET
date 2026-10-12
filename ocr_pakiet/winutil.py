"""Funkcje systemowe Windows: wyszukanie okna ZS, zrzut okna, przewijanie kółkiem."""
from __future__ import annotations

import ctypes
import re
import time

from PIL import Image, ImageGrab

import win32api
import win32con
import win32gui
import win32ui

PW_RENDERFULLCONTENT = 0x00000002


def set_dpi_aware() -> None:
    """Współrzędne w fizycznych pikselach (ważne przy skalowaniu ekranu 125%/150%)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def find_order_window(title_regex: str) -> tuple[int, str] | None:
    """Okno zamówienia: aktywne, jeśli pasuje; inaczej najwyżej położone pasujące."""
    rx = re.compile(title_regex, re.IGNORECASE)
    fg = win32gui.GetForegroundWindow()
    if fg and rx.search(win32gui.GetWindowText(fg) or "") and not win32gui.IsIconic(fg):
        return fg, win32gui.GetWindowText(fg)
    found: list[tuple[int, str]] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            t = win32gui.GetWindowText(hwnd) or ""
            if rx.search(t):
                found.append((hwnd, t))
        return True

    win32gui.EnumWindows(cb, None)  # kolejność = od okna na wierzchu
    return found[0] if found else None


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    return win32gui.GetWindowRect(hwnd)


def _print_window(hwnd: int) -> Image.Image | None:
    l, t, r, b = window_rect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    try:
        ok = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)
        info = bmp.GetInfo()
        data = bmp.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), data, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
    if not ok:
        return None
    # niektóre programy zwracają czarny obraz – wtedy zrzut z ekranu
    small = img.convert("L").resize((64, 32))
    if max(small.getdata()) < 16:
        return None
    return img


def capture(hwnd: int) -> Image.Image | None:
    """Zrzut okna. PrintWindow działa nawet gdy okno jest częściowo zasłonięte."""
    img = None
    try:
        img = _print_window(hwnd)
    except Exception:
        img = None
    if img is None:
        l, t, r, b = window_rect(hwnd)
        img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
    return img


def bring_to_front(hwnd: int) -> None:
    try:
        # sztuczka z ALT pozwala oddać fokus innemu oknu
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    finally:
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.15)


def wheel_at(hwnd: int, x: int, y: int, notches: int) -> None:
    """Przewija kółkiem myszy w punkcie (x, y) okna (współrzędne zrzutu).
    notches > 0 = w dół. Kursor wraca na miejsce."""
    l, t, _, _ = window_rect(hwnd)
    old = win32api.GetCursorPos()
    try:
        win32api.SetCursorPos((l + x, t + y))
        time.sleep(0.03)
        step = -win32con.WHEEL_DELTA if notches > 0 else win32con.WHEEL_DELTA
        for _ in range(abs(notches)):
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, step, 0)
            time.sleep(0.02)
    finally:
        win32api.SetCursorPos(old)

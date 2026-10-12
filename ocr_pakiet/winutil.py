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


GA_ROOT = 2
WM_MDIGETACTIVE = 0x0229


def order_window_info(hwnd: int | None, title_regex: str) -> tuple[int, str] | None:
    """(hwnd, tytuł), jeśli okno nadal istnieje, jest widoczne, nie jest zminimalizowane
    i ma tytuł zamówienia sprzedaży."""
    if not hwnd or not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
        return None
    if not win32gui.IsWindowVisible(hwnd):
        return None
    title = win32gui.GetWindowText(hwnd) or ""
    if not re.search(title_regex, title, re.IGNORECASE):
        return None
    return hwnd, title


def _children(parent: int) -> list[int]:
    out: list[int] = []
    try:
        win32gui.EnumChildWindows(parent, lambda h, _: out.append(h) or True, None)
    except Exception:  # okno bez dzieci
        pass
    return out  # kolejność: od okna na wierzchu


def _order_child(parent: int, title_regex: str) -> tuple[int, str] | None:
    """ZS otwarte WEWNĄTRZ głównego okna Comarch ERP XL (okno dokumentu w oknie programu).
    Zwraca je tylko wtedy, gdy to ono jest aktywnym dokumentem."""
    children = _children(parent)
    matches = [h for h in children if order_window_info(h, title_regex)]
    if not matches:
        return None
    # klasyczny interfejs wielu dokumentów: pytamy kontener, który dokument jest aktywny
    mdi_clients = [h for h in children if win32gui.GetClassName(h) == "MDIClient"]
    for mdi in mdi_clients:
        active = win32gui.SendMessage(mdi, WM_MDIGETACTIVE, 0, 0)
        if active:
            for h in matches:
                if h == active or win32gui.IsChild(active, h):
                    return order_window_info(h, title_regex)
            return None  # aktywny jest inny dokument (np. lista zamówień)
    # inny rodzaj okien dokumentów – bierzemy ZS położone najwyżej
    return order_window_info(matches[0], title_regex)


def active_order_window(title_regex: str) -> tuple[int, str] | None:
    """Okno ZS tylko wtedy, gdy obsługa w nim pracuje: samo jest aktywne albo jest
    aktywnym dokumentem w aktywnym oknie Comarch ERP XL."""
    fg = win32gui.GetForegroundWindow()
    if not fg:
        return None
    return order_window_info(fg, title_regex) or _order_child(fg, title_regex)


def describe_windows() -> str:
    """Opis aktywnego okna i jego okien wewnętrznych (diagnoza: OCR-PAKIET.exe --okna)."""
    fg = win32gui.GetForegroundWindow()
    lines = [f"Aktywne okno: [{win32gui.GetClassName(fg)}] {win32gui.GetWindowText(fg)!r}"]
    for h in _children(fg):
        t = win32gui.GetWindowText(h)
        if not t:
            continue
        l, tp, r, b = win32gui.GetWindowRect(h)
        vis = "widoczne" if win32gui.IsWindowVisible(h) else "ukryte"
        lines.append(f"  [{win32gui.GetClassName(h)}] {t!r}  {r - l}x{b - tp} {vis}")
    return "\n".join(lines)


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
    root = win32gui.GetAncestor(hwnd, GA_ROOT) or hwnd  # ZS wewnątrz XL -> okno programu
    try:
        # sztuczka z ALT pozwala oddać fokus innemu oknu
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(root)
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

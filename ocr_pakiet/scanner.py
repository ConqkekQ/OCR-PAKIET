"""Pełny skan zamówienia: automatyczne przewinięcie listy pozycji od góry do dołu.

Nakładka ustawia kursor nad listą pozycji, przewija kółkiem myszy (bez klikania,
więc zaznaczenie i dane w XL pozostają nietknięte), robi zrzut po każdym kroku
i składa wszystkie pozycje w jedną listę. Na koniec wraca na górę listy.
"""
from __future__ import annotations

import time

from . import winutil
from .reader import GridReader, ReadResult


def full_scan(hwnd: int, reader: GridReader, notches_cfg: int = 0, max_steps: int = 60,
              progress=None) -> tuple[dict[int, str], str]:
    img = winutil.capture(hwnd)
    first = reader.read(img)
    if first.layout is None:
        return {}, first.error or "Nie znaleziono listy pozycji"
    lay = first.layout
    gx = (lay.x0 + lay.x1) // 2
    gy = (lay.y0 + lay.y1) // 2

    winutil.bring_to_front(hwnd)
    winutil.wheel_at(hwnd, gx, gy, -200)  # na samą górę
    time.sleep(0.25)

    rows: dict[int, str] = {}
    unchanged = 0
    res: ReadResult | None = None
    for step in range(max_steps):
        img = winutil.capture(hwnd)
        res = reader.read(img)
        before = len(rows)
        for r in res.rows:
            rows[r.lp] = r.code
        if progress:
            progress(len(rows))
        if res.reached_end:
            break
        unchanged = unchanged + 1 if len(rows) == before else 0
        if unchanged >= 2:
            break  # przewijanie nic nie zmienia – jesteśmy na dole
        visible = max(1, len(res.rows))
        # kółko przewija zwykle 3 wiersze na ząbek; zostawiamy zakładkę 2–3 wierszy
        notches = notches_cfg or max(1, (visible - 3) // 3)
        winutil.wheel_at(hwnd, gx, gy, notches)
        time.sleep(0.25)

    winutil.wheel_at(hwnd, gx, gy, -200)  # powrót na górę
    return rows, ""

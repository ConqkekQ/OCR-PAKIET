"""Odczyt pozycji (Lp. + kod towaru) z obrazu okna zamówienia sprzedaży.

Kroki:
1. Znalezienie nagłówka siatki (kolumny "Lp.", "Towar", "Nazwa") na całym oknie.
2. Wycięcie wąskiego paska z kolumnami Lp. i Towar, rozjaśnienie zaznaczonego
   (niebieskiego) wiersza i powiększenie obrazu.
3. OCR paska i rozbicie każdej linii na numer Lp. i kod towaru.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

from .ocr_engine import OcrEngine, Word
from .packages import levenshtein


@dataclass
class GridLayout:
    x0: int
    x1: int
    y0: int
    y1: int
    win_size: tuple


@dataclass
class Row:
    lp: int
    code: str
    y: float  # środek wiersza w pikselach okna


@dataclass
class ReadResult:
    rows: list[Row] = field(default_factory=list)
    layout: GridLayout | None = None
    reached_end: bool = False  # pod ostatnim wierszem jest pusta przestrzeń siatki
    row_height: float = 18.0
    error: str = ""


_DIGIT_MAP = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0", "I": "1", "l": "1", "|": "1",
                            "i": "1", "!": "1", "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _as_lp(token: str) -> int | None:
    t = token.strip(".,:;'\"`()[]").translate(_DIGIT_MAP)
    if 1 <= len(t) <= 6 and t.isdigit():
        v = int(t)
        return v if v > 0 else None
    return None


def parse_line(words: list[Word]) -> tuple[int, str] | None:
    """Zamienia linię OCR na (Lp, kod). Zwraca None dla linii, które nie są pozycją."""
    words = sorted(words, key=lambda w: w.x)
    tokens = [w.text.strip() for w in words if w.text.strip()]
    if len(tokens) < 1:
        return None
    first = tokens[0]
    lp = _as_lp(first)
    rest = tokens[1:]
    if lp is None and len(first) > 4:
        # Lp. i kod sklejone w jedno słowo, np. "00001LHPINMV25" (Lp. w XL ma 5 cyfr,
        # ale OCR potrafi dodać lub zgubić jedno zero)
        for n in (5, 6, 4):
            if len(first) > n and (cand := _as_lp(first[:n])) is not None:
                lp, rest = cand, [first[n:]] + rest
                break
    if lp is None or not rest:
        return None
    code = "".join(rest).upper()
    code = re.sub(r"[^A-Z0-9._/\-]", "", code).strip("._-/")
    if len(code) < 3:
        return None
    return lp, code


class GridReader:
    def __init__(self, engine: OcrEngine, cfg):
        self.engine = engine
        self.cfg = cfg
        self.layout: GridLayout | None = None
        self.last_header_lines: list[str] = []
        self._debug_dir = None
        if cfg.debug_zapis_obrazow:
            from .config import app_dir

            self._debug_dir = os.path.join(app_dir(), "debug")
            os.makedirs(self._debug_dir, exist_ok=True)

    # ---------- nagłówek siatki ----------
    def find_layout(self, img: Image.Image) -> GridLayout | None:
        # kolumny Lp./Towar/Nazwa są po lewej – czytamy lewą połowę okna, powiększoną 2x
        region = img.crop((0, 0, int(img.width * 0.5), img.height))
        scale = min(2.0, (self.engine.max_dim - 10) / max(region.size))
        work = region.convert("L").resize(
            (int(region.width * scale), int(region.height * scale)), Image.LANCZOS)
        lines = self.engine.read(work)
        words = [w for ln in lines for w in ln]
        self.last_header_lines = [" ".join(w.text for w in ln) for ln in lines]  # do diagnozy
        inv = 1 / scale

        def find(label: str) -> list[Word]:
            # OCR potrafi przekręcić nagłówek (np. "Nazv,'a"), więc dopuszczamy 1 błąd
            target = _norm(label)
            tol = 1 if len(target) >= 4 else 0
            return [w for w in words if levenshtein(_norm(w.text), target, tol) <= tol]

        kod_cands = sorted(find(self.cfg.kolumna_kod), key=lambda w: w.y)
        if not kod_cands:
            return None
        t = kod_cands[0]
        naz = [n for n in find(self.cfg.kolumna_nastepna) if abs(n.cy - t.cy) < 1.5 * t.h and n.x > t.x]
        lps = [p for p in find(self.cfg.kolumna_lp) if abs(p.cy - t.cy) < 1.5 * t.h and p.x < t.x]
        lp = max(lps, key=lambda p: p.x) if lps else None

        y0 = t.y + t.h + 3
        # dół siatki: etykieta "Filtr" pod listą, a jeśli jej nie ma – dół okna
        filtr = [w for w in words if _norm(w.text).startswith("filtr") and w.y > t.y]
        y1 = (min(f.y for f in filtr) - 22) if filtr else work.height - 60 * scale

        # lewa krawędź: kolumna Lp. (numery stoją tuż przed kodem)
        x0 = (min(lp.x, t.x - 70 * scale) if lp else t.x - 70 * scale) - 6
        # prawa krawędź: początek kolumny Nazwa, a gdy OCR jej nie znalazł –
        # koniec najdłuższego kodu pod nagłówkiem "Towar"
        if naz:
            x1 = min(n.x for n in naz) - 3
        else:
            codes = [w for w in words if y0 <= w.y <= y1 and abs(w.x - t.x) < 12 * scale]
            right = max((w.x + w.w for w in codes), default=t.x + 110 * scale)
            x1 = right + 4 * scale
        lay = GridLayout(
            x0=max(0, int(x0 * inv)),
            x1=int(x1 * inv),
            y0=int(y0 * inv),
            y1=int(y1 * inv),
            win_size=img.size,
        )
        if lay.x1 - lay.x0 < 40 or lay.y1 - lay.y0 < 30:
            return None
        return lay

    # ---------- przygotowanie obrazu ----------
    @staticmethod
    def _prepare(crop: Image.Image, scale: float) -> Image.Image:
        arr = np.asarray(crop.convert("RGB")).astype(np.int16)
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        gray = (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)
        # wiersze z niebieskim tłem zaznaczenia: biały tekst -> odwracamy jasność
        blue = (b > 120) & (b - r > 60) & (b - g > 20)
        row_ratio = blue.mean(axis=1)
        sel = row_ratio > 0.35
        if sel.any():
            band = 255 - gray[sel].astype(np.float32)
            # tło zaznaczenia po odwróceniu jest szare – rozciągamy je do bieli
            bg = float(np.median(band))
            band = np.clip(band * (255.0 / max(bg, 1.0)), 0, 255)
            # pionowe linie siatki w zaznaczonym wierszu (ciemne na całej wysokości) -> białe
            dark_cols = (band < 128).mean(axis=0) > 0.8
            band[:, dark_cols] = 255
            gray[sel] = band.astype(np.uint8)
        out = Image.fromarray(gray, "L")
        out = ImageOps.autocontrast(out, cutoff=1)
        if scale != 1:
            out = out.resize((int(out.width * scale), int(out.height * scale)), Image.LANCZOS)
        return out

    # ---------- odczyt ----------
    def read(self, img: Image.Image) -> ReadResult:
        res = ReadResult()
        if self.layout is None or self.layout.win_size != img.size:
            self.layout = self.find_layout(img)
        if self.layout is None:
            res.error = ("Nie widzę nagłówka listy pozycji (kolumny Lp. / Towar / Nazwa). "
                         "Otwórz zakładkę Ogólne zamówienia i przewiń listę maksymalnie w lewo.")
            return res
        lay = self.layout
        crop = img.crop((lay.x0, lay.y0, lay.x1, lay.y1))
        scale = min(self.cfg.skala, (self.engine.max_dim - 10) / max(crop.size))
        prep = self._prepare(crop, scale)
        if self._debug_dir:
            prep.save(os.path.join(self._debug_dir, f"pasek_{int(time.time()*1000)}.png"))
        lines = self.engine.read(prep)

        rows: list[Row] = []
        for ln in lines:
            parsed = parse_line(ln)
            if not parsed:
                continue
            lp, code = parsed
            cy = sum(w.cy for w in ln) / len(ln) / scale + lay.y0
            rows.append(Row(lp, code, cy))
        rows.sort(key=lambda r: r.y)
        rows = _fix_lp_sequence(rows)
        res.rows = rows
        res.layout = lay
        if len(rows) >= 2:
            res.row_height = max(8.0, float(np.median(np.diff([r.y for r in rows]))))
        if rows:
            space_below = lay.y1 - rows[-1].y
            res.reached_end = space_below > 2.5 * res.row_height
        else:
            # pusta siatka albo nieczytelna – zgubiony układ? przy następnym odczycie szukamy od nowa
            self.layout = None
        return res


def _fix_lp_sequence(rows: list[Row]) -> list[Row]:
    """Wiersze na ekranie mają kolejne Lp. Poprawia pojedyncze błędy OCR w numerach
    na podstawie sąsiadów i usuwa duplikaty."""
    if len(rows) < 3:
        return rows
    ys = [r.y for r in rows]
    rh = float(np.median(np.diff(ys)))
    if rh <= 0:
        return rows
    # numer wiersza na ekranie liczony z położenia (odporne na pominięty wiersz)
    idx = [round((y - ys[0]) / rh) for y in ys]
    offsets = [r.lp - i for r, i in zip(rows, idx)]
    base = max(set(offsets), key=offsets.count)
    if offsets.count(base) >= len(rows) / 2:
        for r, i in zip(rows, idx):
            r.lp = base + i
    seen, out = set(), []
    for r in rows:
        if r.lp not in seen:
            seen.add(r.lp)
            out.append(r)
    return out

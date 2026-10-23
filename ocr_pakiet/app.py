"""Okienko podpowiedzi pakietów – zawsze na wierzchu, obok Comarch ERP XL."""
from __future__ import annotations

import hashlib
import os
import queue
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox

from . import __copyright__, __version__
from .config import DOMYSLNY_PLIK_PAKIETOW, Config, package_source, resource
from .ocr_engine import create_engine
from .order_state import OrderState, order_key
from .packages import PackageBook
from .promo import GRATIS, INFO, MIX, RABAT, parse
from .reader import GridReader

BG = "#f7f7f5"
FG = "#1f2328"
MUTED = "#6b7078"
OK = "#1a7f37"
TODO = "#b35900"
ACCENT = "#0b5cad"
WARN = "#a40e26"
NEW_RING = "#ffd54a"
NEW_TAG = "#8a5300"
CARD_BORDER = "#d8dbe0"
# typ promocji -> (tło karty, kolor paska i plakietki)
PROMO_STYLE = {
    GRATIS: ("#f1faf3", "#1a7f37"),
    RABAT: ("#f0f6fd", "#0b5cad"),
    MIX: ("#f6f1fc", "#6e3fb0"),
    INFO: ("#f4f5f7", "#6b7078"),
}
HIGHLIGHT_S = 3.0  # jak długo świeci nowa promocja


class Worker(threading.Thread):
    """Wątek w tle: zrzut okna -> OCR -> stan zamówienia -> podpowiedzi."""

    def __init__(self, cfg: Config, out: queue.Queue):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.out = out
        self.paused = threading.Event()
        self.scan_request = threading.Event()
        self.reset_request = threading.Event()
        self.reload_request = threading.Event()
        self.source_request = threading.Event()  # zmieniono ścieżkę pliku pakietów
        self.state = OrderState()
        self._last_hash = None
        self._last_win = None
        self._status = ""

    def _announce(self, engine, src):
        self.out.put(("engine", f"{engine.name} · pakietów: {len(src.book.packages)}"))
        problem = src.status if (not src.ok or src.status.startswith("⚠")) else ""
        self.out.put(("pkg", problem))

    def _set_status(self, status: str) -> bool:
        """Zapamiętuje stan; zwraca True, gdy się zmienił (komunikat wysyłamy raz)."""
        changed = status != self._status
        self._status = status
        return changed

    def run(self):
        import ctypes

        from . import winutil

        try:  # Windows OCR (WinRT) w wątku pobocznym wymaga zainicjowanego COM
            ctypes.windll.ole32.CoInitializeEx(None, 0)
        except Exception:
            pass
        try:
            engine = create_engine(self.cfg.ocr_silnik, self.cfg.ocr_jezyki, self.cfg.tesseract_sciezka)
            reader = GridReader(engine, self.cfg)
            src = package_source(self.cfg)
        except Exception as e:  # noqa: BLE001
            self.out.put(("fatal", str(e)))
            return
        self._announce(engine, src)
        self._book = src.book
        reader.code_fixer = lambda c: self._book.matcher.match(c) if self._book else None

        while True:
            try:
                if self.source_request.is_set():
                    self.source_request.clear()
                    src = package_source(self.cfg)
                    self._last_hash = None
                    self._announce(engine, src)
                    self._publish(src.book)
                force = self.reload_request.is_set()
                self.reload_request.clear()
                if src.refresh(force=force):
                    self._last_hash = None
                    self._announce(engine, src)
                    if self.state.rows:
                        self._publish(src.book)
                book = src.book
                if book is not self._book:
                    self._book = book
                    reader._retry_cache.clear()
                if self.reset_request.is_set():
                    self.reset_request.clear()
                    self.state.reset(self.state.key)
                    self._last_hash = None

                rx = self.cfg.okno_tytul_regex
                # zrzuty robimy tylko, gdy okno ZS jest aktywne (obsługa w nim pracuje)
                win = winutil.active_order_window(rx)
                if win:
                    self._last_win = win[0]

                if self.scan_request.is_set():
                    self.scan_request.clear()
                    # kliknięcie przycisku aktywuje nakładkę, więc skanujemy ostatnie aktywne ZS
                    target = win or winutil.order_window_info(self._last_win, rx)
                    if target:
                        self._full_scan(target[0], target[1], reader, book)
                    else:
                        self.out.put(("warn", "Najpierw kliknij w okno zamówienia (ZS) w XL"))
                elif win:
                    if self._set_status("active"):
                        self.out.put(("hint", "Odczyt aktywny"))
                    if not self.paused.is_set():
                        self._quick_read(win[0], win[1], reader, book)
                elif winutil.order_window_info(self._last_win, rx):
                    if self._set_status("inactive"):
                        self.out.put(("hint", "Okno ZS nieaktywne – odczyt wstrzymany (kliknij w zamówienie)"))
                else:
                    self._last_win = None
                    if self._set_status("none"):
                        self.out.put(("idle", "Otwórz zamówienie sprzedaży (ZS) w Comarch ERP XL"))
            except Exception as e:  # noqa: BLE001
                self.out.put(("error", f"{e}\n{traceback.format_exc(limit=2)}"))
            time.sleep(self.cfg.interwal_s)

    def _quick_read(self, hwnd, title, reader: GridReader, book: PackageBook):
        from . import winutil

        img = winutil.capture(hwnd)
        if img is None:
            return
        h = hashlib.md5(img.resize((160, 80)).tobytes()).hexdigest() + title
        if h == self._last_hash:
            return  # nic się nie zmieniło na ekranie
        self._last_hash = h
        res = reader.read(img)
        if res.error:
            self.out.put(("warn", res.error))
            return
        self.state.apply(res, title)
        self._publish(book)

    def _full_scan(self, hwnd, title, reader: GridReader, book: PackageBook):
        from .scanner import full_scan

        self.out.put(("busy", "Pełny skan – nie ruszaj myszą…"))
        rows, err = full_scan(hwnd, reader, self.cfg.pelny_skan_zabki,
                              progress=lambda n: self.out.put(("busy", f"Pełny skan… odczytano {n} poz.")))
        if err:
            self.out.put(("warn", err))
            return
        self.state.replace(rows, order_key(title))
        self._last_hash = None
        self._publish(book)

    def _publish(self, book: PackageBook):
        matched: dict[int, str] = {}
        for lp, code in self.state.rows.items():
            m = book.matcher.match(code)
            if m:
                matched[lp] = m
        suggestions = book.suggest(set(matched.values()))
        lp_of: dict[str, int] = {}
        for lp, code in sorted(matched.items()):
            lp_of.setdefault(code, lp)
        new_codes = {matched[lp] for lp in self.state.new_lps if lp in matched}
        self.out.put(("result", {
            "lp_of": lp_of,
            "new_codes": new_codes,
            "key": self.state.key,
            "count": len(self.state.rows),
            "max_lp": max(self.state.rows) if self.state.rows else 0,
            "missing": self.state.missing_lps(),
            "complete": self.state.complete,
            "suggestions": suggestions,
            "names": book.names,
        }))


class App:
    def __init__(self):
        from . import winutil

        winutil.set_dpi_aware()  # przed utworzeniem okna Tk
        self.cfg = Config.load()
        self.q: queue.Queue = queue.Queue()
        self.worker = Worker(self.cfg, self.q)
        self.pkg_warn = ""

        root = self.root = tk.Tk()
        root.title("Pakiety – podpowiedzi")
        ico = resource("assets", "ikona.ico")
        if ico:
            try:
                root.iconbitmap(ico)
            except tk.TclError:
                pass
        root.configure(bg=BG)
        root.attributes("-topmost", True)  # zwykłe okno: minimalizacja, pasek zadań, zamykanie
        k = max(1.0, root.winfo_fpixels("1i") / 96)  # skalowanie ekranu (125%, 150%…)
        sw = root.winfo_screenwidth()
        w, h = int(380 * k), int(560 * k)
        root.geometry(f"{w}x{h}+{sw - w - int(20 * k)}+{int(80 * k)}")
        root.minsize(int(300 * k), int(260 * k))

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.lbl_order = tk.Label(top, text="—", bg=BG, fg=FG, font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_order.pack(fill="x")
        self.lbl_info = tk.Label(top, text="Uruchamianie…", bg=BG, fg=MUTED, font=("Segoe UI", 9),
                                 anchor="w", justify="left", wraplength=int(350 * k))
        self.lbl_info.pack(fill="x")

        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=10, pady=4)
        btn = dict(font=("Segoe UI", 9), relief="flat", bd=0, padx=8, pady=4, cursor="hand2")
        tk.Button(bar, text="⤓ Pełny skan", bg=ACCENT, fg="white", activebackground="#0a4f94",
                  activeforeground="white", command=self.worker.scan_request.set, **btn).pack(side="left")
        self.btn_pause = tk.Button(bar, text="⏸ Pauza", bg="#e4e6ea", fg=FG, command=self.toggle_pause, **btn)
        self.btn_pause.pack(side="left", padx=4)
        tk.Button(bar, text="Wyczyść", bg="#e4e6ea", fg=FG, command=self.worker.reset_request.set,
                  **btn).pack(side="left")
        tk.Button(bar, text="⚙", bg="#e4e6ea", fg=FG, command=self.open_settings,
                  **btn).pack(side="right")
        tk.Button(bar, text="↻ Pakiety", bg="#e4e6ea", fg=FG, command=self.worker.reload_request.set,
                  **btn).pack(side="right", padx=4)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=(10, 4), pady=(4, 4))
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(body, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards = tk.Frame(self.canvas, bg=BG)
        self._cards_win = self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
        self.cards.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.k = k
        self.last_data: dict | None = None
        self.new_until: dict[str, float] = {}  # kod -> do kiedy podświetlać
        self._unhighlight_job = None

        self.lbl_foot = tk.Label(root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.lbl_foot.pack(fill="x", padx=10, pady=(0, 6))
        self._render_message("Szukam okna zamówienia…")

    # ---------- akcje ----------
    def toggle_pause(self):
        if self.worker.paused.is_set():
            self.worker.paused.clear()
            self.btn_pause.configure(text="⏸ Pauza")
        else:
            self.worker.paused.set()
            self.btn_pause.configure(text="▶ Wznów")

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Ustawienia")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.transient(self.root)
        win.resizable(False, False)
        pad = dict(padx=12, pady=4)
        tk.Label(win, text="Plik z pakietami (Excel):", bg=BG, fg=FG, font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", padx=12, pady=(12, 2))
        var = tk.StringVar(value=self.cfg.plik_pakietow)
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", **pad)
        entry = tk.Entry(row, textvariable=var, width=48, font=("Segoe UI", 9))
        entry.pack(side="left", fill="x", expand=True)

        def browse():
            start = os.path.dirname(var.get()) if os.path.isdir(os.path.dirname(var.get())) else None
            path = filedialog.askopenfilename(parent=win, title="Wybierz plik pakietów",
                                              initialdir=start,
                                              filetypes=[("Excel", "*.xlsx *.xlsm"), ("Wszystkie", "*.*")])
            if path:
                var.set(os.path.normpath(path))

        tk.Button(row, text="Przeglądaj…", command=browse, font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
        tk.Label(win, text=f"Domyślnie: {DOMYSLNY_PLIK_PAKIETOW}", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=12)

        def save():
            path = var.get().strip().strip('"')
            if not path:
                path = DOMYSLNY_PLIK_PAKIETOW
            if not os.path.exists(path) and not messagebox.askyesno(
                    "Ustawienia", f"Nie widzę pliku:\n{path}\n\nZapisać mimo to?", parent=win):
                return
            self.cfg.plik_pakietow = path
            try:
                self.cfg.save()
            except OSError as e:
                messagebox.showerror("Ustawienia", f"Nie udało się zapisać ustawień:\n{e}", parent=win)
                return
            self.worker.source_request.set()
            win.destroy()

        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=12, pady=(10, 12))
        tk.Button(btns, text="Przywróć domyślny", font=("Segoe UI", 9),
                  command=lambda: var.set(DOMYSLNY_PLIK_PAKIETOW)).pack(side="left")
        tk.Button(btns, text="Anuluj", font=("Segoe UI", 9), command=win.destroy).pack(side="right")
        tk.Button(btns, text="Zapisz", font=("Segoe UI", 9, "bold"), bg=ACCENT, fg="white",
                  command=save).pack(side="right", padx=6)
        tk.Frame(win, bg="#d8dbe0", height=1).pack(fill="x", padx=12)
        tk.Label(win, text=f"OCR-PAKIET {__version__}\n{__copyright__}", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8), justify="left", anchor="w").pack(fill="x", padx=12, pady=(6, 10))
        entry.focus_set()

    def copy_code(self, code: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.lbl_foot.configure(text=f"Skopiowano kod: {code}")

    # ---------- rysowanie ----------
    def _on_canvas_resize(self, event):
        self.canvas.itemconfigure(self._cards_win, width=event.width)
        if self.last_data:
            wrap = max(150, event.width - int(40 * self.k))
            for w in self.cards.winfo_children():
                for lbl in getattr(w, "_wrap_labels", []):
                    lbl.configure(wraplength=wrap)

    def _on_wheel(self, event):
        if self.canvas.winfo_height() < self.cards.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _clear_cards(self):
        for w in self.cards.winfo_children():
            w.destroy()

    def _render_message(self, msg: str):
        self._clear_cards()
        tk.Label(self.cards, text=msg, bg=BG, fg=MUTED, font=("Segoe UI", 10), anchor="w",
                 justify="left").pack(fill="x", padx=4, pady=8)

    def _card(self, s, lp: int | None, is_new: bool, names: dict):
        p = s.package
        promo = parse(p.note)
        card_bg, accent = PROMO_STYLE[promo.kind]
        wrap = max(150, self.canvas.winfo_width() - int(40 * self.k))

        ring = tk.Frame(self.cards, bg=NEW_RING if is_new else BG, padx=3 if is_new else 0,
                        pady=3 if is_new else 0)
        ring.pack(fill="x", pady=(0, 8), padx=(0, 2))
        card = tk.Frame(ring, bg=card_bg, highlightthickness=1, highlightbackground=CARD_BORDER)
        card.pack(fill="x", padx=0 if is_new else 3, pady=0)
        tk.Frame(card, bg=accent, width=int(5 * self.k)).pack(side="left", fill="y")
        inner = tk.Frame(card, bg=card_bg)
        inner.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=8)

        # 1) nazwa produktu w kolorze typu promocji
        head = tk.Frame(inner, bg=card_bg)
        head.pack(fill="x")
        if is_new:
            tk.Label(head, text=" NOWA ", bg=NEW_TAG, fg="white", font=("Segoe UI", 8, "bold")).pack(
                side="right", anchor="n", padx=(6, 0))
        title = p.name[7:] if p.name.lower().startswith("pakiet ") else p.name
        name_lbl = tk.Label(head, text=title, bg=card_bg, fg=accent, font=("Segoe UI", 11, "bold"),
                            anchor="w", justify="left", wraplength=wrap - (int(50 * self.k) if is_new else 0))
        name_lbl.pack(side="left", fill="x")
        wraps = [name_lbl]

        # 2) jak wygląda pakiet – pełny opis z kolumny Uwagi
        if p.note:
            note_lbl = tk.Label(inner, text=p.note, bg=card_bg, fg=FG, font=("Segoe UI", 10, "bold"),
                                anchor="w", justify="left", wraplength=wrap)
            note_lbl.pack(fill="x", pady=(4, 0))
            wraps.append(note_lbl)

        # 3) Lp. · kod · firma (+ termin)
        meta = tk.Frame(inner, bg=card_bg)
        meta.pack(fill="x", pady=(6, 0))
        if lp is not None:
            tk.Label(meta, text=f"Lp. {lp}  ·", bg=card_bg, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        codes = [it.code for it in p.items]
        for i, code in enumerate(codes[:3]):
            c = tk.Label(meta, text=code, bg=card_bg, fg=ACCENT, font=("Segoe UI", 9, "underline"),
                         cursor="hand2")
            c.pack(side="left", padx=(4, 0))
            c.bind("<Button-1>", lambda e, code=code: self.copy_code(code))
        if p.producer:
            tk.Label(meta, text=f"·  {p.producer}", bg=card_bg, fg=MUTED, font=("Segoe UI", 9)).pack(
                side="left", padx=(4, 0))
        if promo.deadline:
            tk.Label(meta, text=f"⏰ do {promo.deadline}", bg=card_bg, fg=WARN,
                     font=("Segoe UI", 9, "bold")).pack(side="right")

        if len(p.items) > 1:  # pakiet z kilku towarów – co jest, czego brakuje
            for it in p.items:
                nm = it.name or names.get(it.code, "")
                have = it not in s.missing
                txt = f"{'✔ jest ' if have else '➕ dodaj'}  {it.code}  {nm}"
                lbl = tk.Label(inner, text=txt, bg=card_bg, fg=OK if have else TODO,
                               font=("Segoe UI", 9, "normal" if have else "bold"), anchor="w",
                               justify="left", wraplength=wrap, cursor="hand2")
                lbl.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, code=it.code: self.copy_code(code))
                wraps.append(lbl)
        ring._wrap_labels = wraps

    def render(self, d: dict):
        self.last_data = d
        self.lbl_order.configure(text=d["key"] or "Zamówienie")
        info = f"Odczytane pozycje: {d['count']}"
        if d["max_lp"]:
            info += f" (Lp. 1–{d['max_lp']})"
        if d["missing"]:
            miss = ", ".join(map(str, d["missing"][:12])) + ("…" if len(d["missing"]) > 12 else "")
            info += f"\n⚠ Nieodczytane Lp.: {miss} – przewiń listę lub użyj Pełnego skanu"
            self.lbl_info.configure(fg=WARN)
        elif not d["complete"]:
            info += "\nLista może być dłuższa – przewiń w dół lub użyj Pełnego skanu"
            self.lbl_info.configure(fg=TODO)
        else:
            info += " ✓ cała lista"
            self.lbl_info.configure(fg=MUTED)
        if self.pkg_warn:
            info += f"\n{self.pkg_warn}"
            self.lbl_info.configure(fg=WARN)
        self.lbl_info.configure(text=info)

        now = time.monotonic()
        for code in d.get("new_codes", ()):
            self.new_until[code] = now + HIGHLIGHT_S
        self.new_until = {c: t for c, t in self.new_until.items() if t > now}

        sugg = d["suggestions"]
        lp_of = d.get("lp_of", {})

        def first_lp(s):
            lps = [lp_of[i.code] for i in s.present if i.code in lp_of]
            return min(lps) if lps else 10**9

        sugg = sorted(sugg, key=first_lp)  # kolejność jak pozycje w ZS
        self.root.title(f"Pakiety – podpowiedzi ({len(sugg)})" if sugg else "Pakiety – podpowiedzi")
        self._clear_cards()
        if not sugg:
            self._render_message("Brak promocji dla towarów w tym zamówieniu.")
        for s in sugg:
            lp = first_lp(s)
            is_new = any(self.new_until.get(i.code, 0) > now for i in s.present)
            self._card(s, None if lp == 10**9 else lp, is_new, d["names"])
        if any(t > now for t in self.new_until.values()):
            if self._unhighlight_job:
                self.root.after_cancel(self._unhighlight_job)
            delay = int((min(t for t in self.new_until.values() if t > now) - now) * 1000) + 50
            self._unhighlight_job = self.root.after(delay, self._rerender_last)
        self.lbl_foot.configure(text=f"Odświeżono {time.strftime('%H:%M:%S')} · kliknij kod, aby go skopiować")

    def _rerender_last(self):
        self._unhighlight_job = None
        if self.last_data:
            d = dict(self.last_data)
            d["new_codes"] = set()
            self.render(d)

    def poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "result":
                    self.render(data)
                elif kind == "idle":
                    self.lbl_order.configure(text="—")
                    self.root.title("Pakiety – podpowiedzi")
                    self.lbl_info.configure(text=data, fg=MUTED)
                elif kind == "pkg":
                    self.pkg_warn = data
                    if data:
                        self.lbl_info.configure(text=data, fg=WARN)
                elif kind == "hint":
                    self.lbl_foot.configure(text=data)
                elif kind in ("warn", "busy"):
                    self.lbl_info.configure(text=data, fg=TODO)
                elif kind == "engine":
                    self.lbl_foot.configure(text=data)
                elif kind == "error":
                    self.lbl_info.configure(text="Błąd: " + data.splitlines()[0], fg=WARN)
                    print(data)
                elif kind == "fatal":
                    messagebox.showerror("Pakiety – błąd uruchomienia", data)
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    def run(self):
        self.worker.start()
        self.root.after(200, self.poll)
        self.root.mainloop()


def _already_running() -> bool:
    """Blokada drugiej kopii (np. autostart + dwuklik na skrót)."""
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\OCR-PAKIET-nakladka")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main():
    if _already_running():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Pakiety", "Nakładka OCR-PAKIET jest już uruchomiona.")
        root.destroy()
        return
    App().run()


def demo_screenshot(path: str) -> int:
    """Rysuje okienko na przykładowych promocjach i zapisuje zrzut (test wyglądu, CI)."""
    from PIL import ImageGrab

    from .packages import Item, Package, Suggestion

    app = App()
    demo = [
        (3, "Pakiet Qivitan 25 mg/ml 100 ml", "TST001", "Livisto", "7+1"),
        (7, "Pakiet Forcyl 160 mg/ml 100ml", "TST002", "Vetoquinol", "12 szt.: -25%"),
        (11, "Pakiet Cefabactin 500mg 10 tabl", "TST003", "Dechra",
         "MIX Dechra: 1500 zł netto: -7% / 3000 zł netto: -10% / 6000 zł netto: -14%"),
        (14, "Pakiet Apoquel 16 mg tabl. powlekane 20 tabl", "TST004", "Zoetis", "1 szt.: -10% (do 27.11.2026)"),
        (18, "Pakiet Rapidexon 0.2% 100ml", "TST005", "Dechra",
         "Pakiet uśredniony – indywidualne warunki u przedstawiciela"),
        (21, "Pakiet Ubrolexin 10g tuba", "TST006", "Boehringer Ingelheim", "10 op.: -10% / 25 op.: -15%"),
    ]
    sugg, lp_of = [], {}
    for lp, name, code, prod, note in demo:
        it = Item(code)
        sugg.append(Suggestion(Package(name, [it], note, prod), [it], []))
        lp_of[code] = lp
    data = {"key": "ZS-1/26/TEST", "count": 23, "max_lp": 23, "missing": [], "complete": True,
            "suggestions": sugg, "names": {}, "lp_of": lp_of, "new_codes": {"TST006"}}
    app.root.geometry(f"{int(400 * app.k)}x{int(820 * app.k)}+20+20")
    app.root.update()
    app.render(data)
    app.root.update()
    app.root.after(600, lambda: None)
    for _ in range(10):
        app.root.update()
        time.sleep(0.05)
    x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
    w, h = app.root.winfo_width(), app.root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
    app.root.destroy()
    return 0

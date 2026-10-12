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
from .reader import GridReader

BG = "#f7f7f5"
FG = "#1f2328"
MUTED = "#6b7078"
OK = "#1a7f37"
TODO = "#b35900"
ACCENT = "#0b5cad"
WARN = "#a40e26"
NOTE_BG = "#ffe9a8"
NOTE_FG = "#4a3200"


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
        self.out.put(("result", {
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
        body.pack(fill="both", expand=True, padx=10, pady=(4, 4))
        self.txt = tk.Text(body, bg="white", fg=FG, font=("Segoe UI", 10), relief="flat", wrap="word",
                           padx=10, pady=8, cursor="arrow", highlightthickness=1,
                           highlightbackground="#d8dbe0")
        sb = tk.Scrollbar(body, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        t = self.txt
        t.tag_configure("pk", font=("Segoe UI", 10, "bold"), spacing1=8)
        t.tag_configure("pk_done", font=("Segoe UI", 10, "bold"), foreground=OK, spacing1=8)
        t.tag_configure("ok", foreground=OK)
        t.tag_configure("todo", foreground=TODO, font=("Segoe UI", 10, "bold"))
        t.tag_configure("code", foreground=ACCENT, underline=True)
        t.tag_configure("muted", foreground=MUTED, font=("Segoe UI", 9))
        t.tag_configure("note", background=NOTE_BG, foreground=NOTE_FG, font=("Segoe UI", 10, "bold"),
                        lmargin1=6, lmargin2=6, rmargin=6, spacing1=3, spacing3=3)
        t.tag_bind("code", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("code", "<Leave>", lambda e: t.configure(cursor="arrow"))
        t.tag_bind("code", "<Button-1>", self.copy_code)

        self.lbl_foot = tk.Label(root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.lbl_foot.pack(fill="x", padx=10, pady=(0, 6))
        self._render_text("Szukam okna zamówienia…", "muted")

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

    def copy_code(self, event):
        idx = self.txt.index(f"@{event.x},{event.y}")
        rng = self.txt.tag_prevrange("code", f"{idx}+1c")
        if not rng:
            return
        code = self.txt.get(*rng).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.lbl_foot.configure(text=f"Skopiowano kod: {code}")

    # ---------- rysowanie ----------
    def _render_text(self, msg: str, tag: str = ""):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", msg, tag)
        self.txt.configure(state="disabled")

    def render(self, d: dict):
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

        t = self.txt
        t.configure(state="normal")
        t.delete("1.0", "end")
        sugg = d["suggestions"]
        names = d["names"]
        if not sugg:
            t.insert("end", "Brak pakietów dla towarów w tym zamówieniu.", "muted")
        for s in sugg:
            p = s.package
            if s.complete:
                t.insert("end", f"✅ {p.name}\n", "pk_done")
            else:
                t.insert("end", f"📦 {p.name}  ({len(s.present)}/{len(p.items)})\n", "pk")
            if p.note:
                t.insert("end", f" ℹ  {p.note}\n", "note")
            for it in p.items:
                nm = it.name or names.get(it.code, "")
                if it in s.missing:
                    t.insert("end", "  ➕ dodaj ", "todo")
                    t.insert("end", it.code, "code")
                else:
                    t.insert("end", "  ✔ jest  ", "ok")
                    t.insert("end", it.code, "ok")
                t.insert("end", f"  {nm}\n" if nm else "\n", "muted")
        t.configure(state="disabled")
        self.lbl_foot.configure(text=f"Odświeżono {time.strftime('%H:%M:%S')} · kliknij kod, aby go skopiować")

    def poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "result":
                    self.render(data)
                elif kind == "idle":
                    self.lbl_order.configure(text="—")
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

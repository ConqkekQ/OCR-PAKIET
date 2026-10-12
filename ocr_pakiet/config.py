"""Konfiguracja aplikacji (plik config.json obok programu)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field


def app_dir() -> str:
    """Folder programu: obok .exe (PyInstaller) albo katalog główny repozytorium."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Domyślny wspólny plik pakietów działu (użytkownik może wskazać inny w ⚙ Ustawieniach)
DOMYSLNY_PLIK_PAKIETOW = r"Z:\PAKIETY\pakiety.xlsx"


@dataclass
class Config:
    # Tytuł okna zamówienia w Comarch ERP XL (wyrażenie regularne)
    okno_tytul_regex: str = r"Zam[óo]wienie sprzeda[żz]y"
    # Wspólny plik z definicjami pakietów (dysk sieciowy). Gdy jest niedostępny,
    # program używa ostatniej kopii zapisanej lokalnie (pakiety_kopia.xlsx).
    plik_pakietow: str = DOMYSLNY_PLIK_PAKIETOW
    # Co ile sekund odczytywać okno w trybie podglądu
    interwal_s: float = 1.5
    # Silnik OCR: "auto", "windows" lub "tesseract"
    ocr_silnik: str = "auto"
    # Język Windows OCR (kody to litery i cyfry, więc wystarczy dowolny łaciński)
    ocr_jezyki: list = field(default_factory=lambda: ["pl", "en-US", "en"])
    # Ścieżka do tesseract.exe (tylko gdy silnik = tesseract i nie ma go w PATH)
    tesseract_sciezka: str = ""
    # Powiększenie wycinka z kodami przed OCR (większe = dokładniej, wolniej)
    skala: float = 3.0
    # Nagłówki kolumn w siatce pozycji ZS
    kolumna_lp: str = "Lp."
    kolumna_kod: str = "Towar"
    kolumna_nastepna: str = "Nazwa"
    # Ile "ząbków" kółka myszy na jeden krok przy pełnym skanie (0 = automatycznie)
    pelny_skan_zabki: int = 0
    # Zapisywać wycinki do folderu debug/ (do diagnozy problemów z odczytem)
    debug_zapis_obrazow: bool = False

    @staticmethod
    def path() -> str:
        return os.path.join(app_dir(), "config.json")

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        p = cls.path()
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        else:
            cfg.save()
        return cfg

    def save(self) -> None:
        with open(self.path(), "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    def resolve(self, name: str) -> str:
        return name if os.path.isabs(name) else os.path.join(app_dir(), name)


def resource(*parts: str) -> str | None:
    """Plik zasobu: obok programu albo spakowany w .exe (PyInstaller)."""
    for base in (app_dir(), getattr(sys, "_MEIPASS", "")):
        p = os.path.join(base, *parts)
        if base and os.path.exists(p):
            return p
    return None


def package_source(cfg: Config):
    from .packages import PackageSource

    if not os.path.isabs(cfg.plik_pakietow):
        ensure_packages_file_local()  # tryb lokalny (np. testy) – plik obok programu z szablonu
    src = PackageSource(
        shared=cfg.resolve(cfg.plik_pakietow),
        cache=os.path.join(app_dir(), "pakiety_kopia.xlsx"),
    )
    src.refresh(force=True)
    return src


def ensure_packages_file_local() -> str:
    """Lokalny pakiety.xlsx obok programu (z szablonu) – ostatnia deska ratunku."""
    import shutil

    path = os.path.join(app_dir(), "pakiety.xlsx")
    if not os.path.exists(path):
        for base in (app_dir(), getattr(sys, "_MEIPASS", "")):
            tpl = os.path.join(base, "pakiety_szablon.xlsx")
            if base and os.path.exists(tpl):
                shutil.copyfile(tpl, path)
                break
    return path

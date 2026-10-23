"""Uruchomienie:
    python -m ocr_pakiet                 – okienko podpowiedzi (tryb normalny)
    python -m ocr_pakiet --obraz zrzut.png  – test odczytu na zapisanym zrzucie ekranu
    OCR-PAKIET.exe --obraz zrzut.png --wynik wynik.txt  – to samo w wersji .exe
"""
from __future__ import annotations

import argparse
import sys


def test_image(path: str) -> int:
    from PIL import Image

    from .config import Config, package_source
    from .ocr_engine import create_engine
    from .reader import GridReader

    cfg = Config.load()
    engine = create_engine(cfg.ocr_silnik, cfg.ocr_jezyki, cfg.tesseract_sciezka)
    print(f"Silnik OCR: {engine.name}")
    reader = GridReader(engine, cfg)
    res = reader.read(Image.open(path).convert("RGB"))
    if res.error:
        print("BŁĄD:", res.error)
        print("\nTekst odczytany z lewej połowy okna (do diagnozy):")
        for ln in reader.last_header_lines[:40]:
            print("  ", ln)
        return 1
    print(f"Obszar listy: {res.layout}")
    print(f"Widać koniec listy: {'tak' if res.reached_end else 'nie'}\n")
    src = package_source(cfg)
    print(src.status)
    book = src.book if src.ok else None
    codes = set()
    for r in res.rows:
        m = book.matcher.match(r.code) if book else None
        if m:
            codes.add(m)
        flag = f"-> {m}" if m and m != r.code else ("(w pakiecie)" if m else "")
        print(f"  Lp {r.lp:>4}  {r.code:<18} {flag}")
    if book:
        print("\nPodpowiedzi:")
        for s in book.suggest(codes):
            stan = "wszystkie towary są w zamówieniu" if s.complete else "brakuje: " + ", ".join(i.code for i in s.missing)
            print(f"  {s.package.name}: {stan}")
    return 0


def check_live_window(save_dir: str | None = None) -> int:
    import time

    from . import winutil
    from .config import Config
    from .ocr_engine import create_engine
    from .reader import GridReader

    winutil.set_dpi_aware()
    time.sleep(5)
    cfg = Config.load()
    print(winutil.describe_windows())
    win = winutil.active_order_window(cfg.okno_tytul_regex)
    if not win:
        print("\nNIE ZNALEZIONO aktywnego okna ZS")
        return 1
    hwnd, title = win
    print(f"\nZnalezione ZS: {title!r}")
    img = winutil.capture(hwnd)
    print(f"Zrzut: {img.size if img else None}")
    engine = create_engine(cfg.ocr_silnik, cfg.ocr_jezyki, cfg.tesseract_sciezka)
    print(f"Silnik OCR: {engine.name}")
    reader = GridReader(engine, cfg)
    res = reader.read(img)
    if save_dir and img is not None:
        import os

        img.save(os.path.join(save_dir, "ocr_zrzut_okna.png"))
        if res.layout:
            lay = res.layout
            reader._prepare(img.crop((lay.x0, lay.y0, lay.x1, lay.y1)), cfg.skala).save(
                os.path.join(save_dir, "ocr_pasek.png"))
        print(f"Zapisano obrazy diagnostyczne w: {save_dir}")
    if res.error:
        print("BŁĄD:", res.error)
        for ln in reader.last_header_lines[:40]:
            print("  ", ln)
        return 1
    print(f"Obszar listy: {res.layout}")
    print(f"Odczytane linie OCR: {reader.last_strip_lines}")
    for r in res.rows:
        print(f"  Lp {r.lp:>4}  {r.code}")
    return 0


def _redirect(path, fn) -> int:
    if not path:
        return fn()
    with open(path, "w", encoding="utf-8") as f:
        sys.stdout = sys.stderr = f
        try:
            return fn()
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            return 2


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # polskie znaki w konsoli Windows
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="ocr_pakiet")
    ap.add_argument("--obraz", help="test odczytu na pliku ze zrzutem okna ZS")
    ap.add_argument("--wynik", help="zapisz wynik testu do pliku (dla wersji .exe bez konsoli)")
    ap.add_argument("--okna", action="store_true",
                    help="po 5 s zapisz opis aktywnego okna (kliknij w tym czasie w XL)")
    ap.add_argument("--sprawdz-okno", action="store_true",
                    help="po 5 s znajdź aktywne ZS na ekranie, odczytaj je i zapisz wynik")
    ap.add_argument("--podglad", help="zapisz zrzut okienka z przykładowymi promocjami (test wyglądu)")
    args = ap.parse_args()
    if args.podglad:
        from .app import demo_screenshot

        return _redirect(args.wynik, lambda: demo_screenshot(args.podglad))
    if args.sprawdz_okno:
        import os

        folder = os.path.dirname(os.path.abspath(args.wynik)) if args.wynik else None
        return _redirect(args.wynik, lambda: check_live_window(folder))
    if args.okna:
        import time

        from . import winutil

        winutil.set_dpi_aware()
        time.sleep(5)
        text = winutil.describe_windows()
        if args.wynik:
            with open(args.wynik, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            print(text)
        return 0
    if args.obraz:
        if args.wynik:
            with open(args.wynik, "w", encoding="utf-8") as f:
                sys.stdout = sys.stderr = f
                try:
                    return test_image(args.obraz)
                except Exception:  # noqa: BLE001
                    import traceback

                    traceback.print_exc()
                    return 2
        return test_image(args.obraz)
    from .app import main as app_main

    app_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

    from .config import Config, ensure_packages_file
    from .ocr_engine import create_engine
    from .packages import PackageBook
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
    try:
        book = PackageBook(ensure_packages_file(cfg))
    except Exception as e:  # noqa: BLE001
        print(f"(Pakiety niewczytane: {e})")
        book = None
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
            stan = "KOMPLET" if s.complete else "brakuje: " + ", ".join(i.code for i in s.missing)
            print(f"  {s.package.name}: {stan}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # polskie znaki w konsoli Windows
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="ocr_pakiet")
    ap.add_argument("--obraz", help="test odczytu na pliku ze zrzutem okna ZS")
    ap.add_argument("--wynik", help="zapisz wynik testu do pliku (dla wersji .exe bez konsoli)")
    args = ap.parse_args()
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

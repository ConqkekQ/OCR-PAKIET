"""Uruchomienie:
    python -m ocr_pakiet                 – okienko podpowiedzi (tryb normalny)
    python -m ocr_pakiet --obraz zrzut.png  – test odczytu na zapisanym zrzucie ekranu
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
    res = GridReader(engine, cfg).read(Image.open(path).convert("RGB"))
    if res.error:
        print("BŁĄD:", res.error)
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
    ap = argparse.ArgumentParser(prog="ocr_pakiet")
    ap.add_argument("--obraz", help="test odczytu na pliku ze zrzutem okna ZS")
    args = ap.parse_args()
    if args.obraz:
        return test_image(args.obraz)
    from .app import main as app_main

    app_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Punkt wejścia dla PyInstaller (zbuduj_exe.bat)."""
import sys

from ocr_pakiet.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

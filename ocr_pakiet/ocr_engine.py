"""Silniki OCR: wbudowany Windows OCR (domyślny) lub Tesseract (zapasowy).

Oba zwracają listę linii, a każda linia to lista słów z położeniem
w pikselach obrazu wejściowego.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from PIL import Image


@dataclass
class Word:
    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


Line = list  # list[Word]


class OcrEngine:
    name = "?"
    max_dim = 10_000

    def read(self, img: Image.Image) -> list[Line]:
        raise NotImplementedError


class WindowsOcr(OcrEngine):
    """Windows.Media.Ocr – wbudowany w Windows 10/11, szybki, bez instalacji."""

    name = "Windows OCR"

    def __init__(self, languages: list[str]):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine as WinEngine

        self._WinEngine = WinEngine
        engine = None
        for lang in languages:
            try:
                if WinEngine.is_language_supported(Language(lang)):
                    engine = WinEngine.try_create_from_language(Language(lang))
                    if engine:
                        self.name = f"Windows OCR ({lang})"
                        break
            except Exception:
                continue
        if engine is None:
            engine = WinEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise RuntimeError(
                "Brak pakietu językowego OCR w Windows. Zainstaluj go poleceniem (PowerShell jako admin):\n"
                'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"'
            )
        self._engine = engine
        self.max_dim = int(WinEngine.max_image_dimension)

    def read(self, img: Image.Image) -> list[Line]:
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter

        img = img.convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(img.tobytes())
        bmp = SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.RGBA8, img.width, img.height
        )

        async def run():
            return await self._engine.recognize_async(bmp)

        result = asyncio.run(run())
        lines: list[Line] = []
        for ln in result.lines:
            words = []
            for w in ln.words:
                r = w.bounding_rect
                words.append(Word(w.text, r.x, r.y, r.width, r.height))
            if words:
                lines.append(words)
        return lines


class TesseractOcr(OcrEngine):
    name = "Tesseract"

    def __init__(self, exe_path: str = ""):
        import pytesseract

        if exe_path:
            pytesseract.pytesseract.tesseract_cmd = exe_path
        pytesseract.get_tesseract_version()  # rzuca wyjątek, gdy brak programu
        self._pt = pytesseract

    def read(self, img: Image.Image) -> list[Line]:
        d = self._pt.image_to_data(
            img.convert("L"),
            config="--psm 6",
            output_type=self._pt.Output.DICT,
        )
        groups: dict[tuple, list[Word]] = {}
        for i, text in enumerate(d["text"]):
            text = (text or "").strip()
            if not text:
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            groups.setdefault(key, []).append(
                Word(text, d["left"][i], d["top"][i], d["width"][i], d["height"][i])
            )
        lines = list(groups.values())
        lines.sort(key=lambda ln: min(w.y for w in ln))
        return lines


def create_engine(kind: str, languages: list[str], tesseract_path: str = "") -> OcrEngine:
    errors = []
    order = {"windows": ["windows"], "tesseract": ["tesseract"]}.get(kind, ["windows", "tesseract"])
    for k in order:
        try:
            if k == "windows":
                return WindowsOcr(languages)
            return TesseractOcr(tesseract_path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{k}: {e}")
    raise RuntimeError("Nie udało się uruchomić OCR:\n" + "\n".join(errors))

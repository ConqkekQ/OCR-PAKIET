"""Rysuje sztuczne okno ZS (bez danych klientów) do testów odczytu.

python tests/syntetyczny_zs.py wyjscie.png
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROWS = [
    ("L008877", "Eficur 50mg/ml, 250 ml, inj."),
    ("MREKLATM100", "Rękawice lateksowe M 100szt. bezpudrowe"),
    ("LHPDIVPEN5", "Divence Penta 1 fiol."),
    ("L002594", "Vetahepar 100 mg/ml inj"),
    ("LHPEFI100", "Eficur 50mg/ml, 100 ml, inj."),
    ("LVAPYRG250", "Pyralgivet inj. 250ml"),
    ("L002591", "Pyralgivet inj. 100ml"),
    ("MREKLATS100", "Rękawice lateksowe S 100szt. bezpudrowe"),
]


def font(size):
    for name in ("tahoma.ttf", "C:/Windows/Fonts/tahoma.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(path, selected=3):
    W, H = 1500, 560
    img = Image.new("RGB", (W, H), (240, 240, 240))
    d = ImageDraw.Draw(img)
    f = font(11)
    d.rectangle((0, 0, W, 28), fill=(205, 222, 240))
    d.text((8, 7), "Zamówienie sprzedaży [ZS-1/26/TEST] - edycja", fill="black", font=f)
    d.rectangle((12, 120, W - 60, H - 70), fill="white", outline=(160, 160, 160))
    hy = 135
    for x, t in ((60, "Lp."), (118, "Towar"), (230, "Nazwa"), (700, "Ilość"), (820, "Cena netto")):
        d.text((x, hy), t, fill="black", font=f)
    y = 160
    for i, (code, name) in enumerate(ROWS, 1):
        txt = "black"
        if i == selected:
            d.rectangle((50, y - 2, W - 62, y + 15), fill=(0, 120, 215))
            txt = "white"
        d.text((84, y), f"{i:05d}", fill=txt, font=f)
        d.text((118, y), code, fill=txt, font=f)
        d.text((230, y), name, fill=txt, font=f)
        d.text((740, y), str(i + 1), fill=txt, font=f)
        y += 18
    d.text((14, H - 55), "Filtr:", fill="black", font=f)
    img.save(path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "syntetyczny_zs.png"
    draw(out)
    print(os.path.abspath(out))

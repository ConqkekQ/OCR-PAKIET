"""Rysuje ikonę programu (assets/ikona.ico): paczka na niebieskim tle."""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, S - 8, S - 8), radius=52, fill=(11, 92, 173))
# pudełko w rzucie izometrycznym
top = [(128, 52), (206, 92), (128, 132), (50, 92)]
left = [(50, 92), (128, 132), (128, 214), (50, 174)]
right = [(128, 132), (206, 92), (206, 174), (128, 214)]
d.polygon(left, fill=(235, 241, 248))
d.polygon(right, fill=(196, 214, 235))
d.polygon(top, fill=(255, 255, 255))
# taśma
d.polygon([(89, 72), (167, 112), (167, 136), (89, 96)], fill=(255, 176, 32))
d.line([(128, 132), (128, 214)], fill=(11, 92, 173), width=4)
img.save("assets/ikona.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save("assets/ikona.png")
print("ok")

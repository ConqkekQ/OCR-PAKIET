"""Tworzy plik z metadanymi .exe (Właściwości -> Szczegóły) dla PyInstaller --version-file.

python narzedzia/wersja_exe.py 0.3.0 version_info.txt
"""
import sys

ver = sys.argv[1] if len(sys.argv) > 1 else "0.0.0"
out = sys.argv[2] if len(sys.argv) > 2 else "version_info.txt"
nums = [int(x) if x.isdigit() else 0 for x in (ver.split(".") + ["0"] * 4)[:4]]
t = tuple(nums)
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041504B0', [
      StringStruct('CompanyName', 'Wojciech Kociuba'),
      StringStruct('FileDescription', 'OCR-PAKIET – podpowiedzi pakietów w Comarch ERP XL'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'OCR-PAKIET'),
      StringStruct('LegalCopyright', '© 2026 Wojciech Kociuba. Wszelkie prawa zastrzeżone.'),
      StringStruct('OriginalFilename', 'OCR-PAKIET.exe'),
      StringStruct('ProductName', 'OCR-PAKIET'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [0x0415, 1200])])
  ]
)
"""
with open(out, "w", encoding="utf-8") as f:
    f.write(text)
print(out)

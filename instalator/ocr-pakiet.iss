; Instalator OCR-PAKIET (Inno Setup 6)
; Budowany automatycznie przez GitHub Actions: iscc /DAppVersion=x.y.z instalator\ocr-pakiet.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{5B7E2C41-8A3F-4C0E-9C55-0C2D7A1B6E31}
AppName=OCR-PAKIET
AppVersion={#AppVersion}
AppVerName=OCR-PAKIET {#AppVersion}
AppPublisher=Wojciech Kociuba
AppCopyright=© 2026 Wojciech Kociuba. Wszelkie prawa zastrzeżone.
DefaultDirName={autopf}\OCR-PAKIET
DefaultGroupName=OCR-PAKIET
DisableProgramGroupPage=yes
DisableDirPage=yes
; instalacja dla bieżącego użytkownika – bez uprawnień administratora
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=OCR-PAKIET-Setup
SetupIconFile=..\assets\ikona.ico
UninstallDisplayIcon={app}\OCR-PAKIET.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Languages]
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "Utwórz skrót na pulpicie"; GroupDescription: "Skróty:"
Name: "autostart"; Description: "Uruchamiaj automatycznie po włączeniu komputera"; GroupDescription: "Uruchamianie:"

[Files]
Source: "..\dist\OCR-PAKIET.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\pakiety_szablon.xlsx"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENCJA.txt"; Flags: ignoreversion
; pakiety program czyta ze wspólnego pliku Z:\PAKIETY\pakiety.xlsx (ustawienie w config.json)

[Icons]
Name: "{group}\OCR-PAKIET"; Filename: "{app}\OCR-PAKIET.exe"
Name: "{group}\Plik pakietów (Excel)"; Filename: "Z:\PAKIETY\pakiety.xlsx"
Name: "{group}\Odinstaluj OCR-PAKIET"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OCR-PAKIET"; Filename: "{app}\OCR-PAKIET.exe"; Tasks: desktopicon
Name: "{userstartup}\OCR-PAKIET"; Filename: "{app}\OCR-PAKIET.exe"; Tasks: autostart

[Run]
Filename: "{app}\OCR-PAKIET.exe"; Description: "Uruchom OCR-PAKIET"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\pakiety_kopia.xlsx"
Type: filesandordirs; Name: "{app}\debug"

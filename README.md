# OCR-PAKIET

Nakładka na **Comarch ERP XL**, która podczas wprowadzania zamówienia sprzedaży (ZS)
odczytuje z ekranu kody towarów i od razu podpowiada, w jakie **pakiety** można je złożyć.
Ilości w zamówieniu są ignorowane: liczy się tylko to, czy towar jest na liście.

Program **tylko czyta ekran**. Nie łączy się z bazą SQL, niczego nie zapisuje w XL
i nie wymaga żadnych licencji Comarcha.

## Jak to działa

1. Co ~1,5 s program sprawdza, czy aktywne jest okno *Zamówienie sprzedaży* (po tytule okna). Zrzut robi tylko wtedy, gdy obsługa pracuje w tym oknie. Gdy ZS jest w tle, zminimalizowane albo zamknięte, program nic nie robi. Zrzut trzymany jest wyłącznie w pamięci i nie zapisuje się na dysku.
2. Znajduje nagłówek listy pozycji (kolumny **Lp.**, **Towar**, **Nazwa**) i wycina pasek z numerami i kodami.
3. Rozpoznaje tekst wbudowanym w Windows silnikiem OCR. Kody są poprawiane o typowe pomyłki (O/0, I/1, S/5), ale **nie** o zamienione cyfry, bo `L002594` i `L002591` to różne towary.
4. Porównuje kody z plikiem `pakiety.xlsx` i pokazuje podpowiedzi w okienku „zawsze na wierzchu”.

Kliknięcie kodu w okienku kopiuje go do schowka, więc można go od razu wkleić w XL.

## Długie zamówienia (przewijanie)

Lista pozycji często nie mieści się na ekranie. Są dwa sposoby, które działają razem:

- **Zbieranie w tle.** Program pamięta pozycje każdego ZS po numerze Lp. Wystarczy przewinąć listę w dół,
  a nakładka dołoży kolejne pozycje. Numer zamówienia bierze z tytułu okna, więc po otwarciu innego ZS zaczyna od nowa.
  Na górze okienka widać, ile pozycji odczytano i czy któregoś Lp. brakuje.
- **Przycisk „⤓ Pełny skan”.** Program sam przewija listę kółkiem myszy od góry do dołu (bez klikania, więc
  zaznaczenie i dane w XL zostają nietknięte), odczytuje każdy ekran i wraca na górę. Trwa kilka sekund;
  w tym czasie nie ruszaj myszą.

Program rozpoznaje koniec listy po pustym miejscu pod ostatnią pozycją.

## Instalacja na stanowisku

1. Wejdź w [Releases](../../releases/latest) i pobierz **`OCR-PAKIET-Setup.exe`**.
2. Uruchom plik i klikaj „Dalej”. Uprawnienia administratora nie są potrzebne.
   Można zaznaczyć skrót na pulpicie i automatyczne uruchamianie z Windowsem.
3. Gotowe: okienko podpowiedzi pojawi się z prawej strony ekranu.

Windows może przy pierwszym uruchomieniu pokazać ostrzeżenie SmartScreen („System Windows ochronił ten komputer”),
bo program nie ma płatnego podpisu cyfrowego. Kliknij **Więcej informacji → Uruchom mimo to**. Jeśli program
zablokuje antywirus, poproś IT o dodanie go do wyjątków.

Aktualizacja: pobierz nowszy `OCR-PAKIET-Setup.exe` i zainstaluj na starą wersję. Plik pakietów i ustawienia zostają.

Program instaluje się w `%LOCALAPPDATA%\Programs\OCR-PAKIET`. Tam leżą `pakiety.xlsx` i `config.json`;
do pliku pakietów jest też skrót w menu Start („Plik pakietów (Excel)”).

**Wersja przenośna:** `OCR-PAKIET.exe` z tej samej strony działa bez instalacji, np. z pendrive’a lub dysku sieciowego.

### Wspólny plik pakietów dla całego działu

Żeby nie uzupełniać pakietów na każdym komputerze osobno, połóż `pakiety.xlsx` na dysku sieciowym i w `config.json`
każdego stanowiska wpisz pełną ścieżkę, np. `"plik_pakietow": "\\\\serwer\\sprzedaz\\pakiety.xlsx"`.
Zmiany w pliku program wczytuje sam.

### Nowa wersja programu (dla opiekuna repozytorium)

GitHub sam buduje instalator po wypchnięciu tagu wersji:

```bash
git tag v0.3.0
git push origin v0.3.0
```

Po kilku minutach w Releases pojawi się `OCR-PAKIET-Setup.exe` i `OCR-PAKIET.exe`.

### Uruchamianie z kodu źródłowego (dla programisty)

1. Zainstaluj [Python 3.10+](https://www.python.org/downloads/) i zaznacz *Add python.exe to PATH*.
2. Uruchom `instaluj.bat`, potem `uruchom.bat`.

Windows OCR potrzebuje pakietu językowego OCR. Zwykle jest zainstalowany razem z językiem polskim lub angielskim.
Jeśli program zgłosi jego brak, uruchom PowerShell jako administrator:

```powershell
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"
```

## Plik pakietów `pakiety.xlsx`

Arkusz **Pakiety**: jeden wiersz = jeden towar w pakiecie.

| Pakiet | Kod towaru | Nazwa towaru | Uwagi |
|---|---|---|---|
| Eficur 250 + 100 | L008877 | Eficur 50mg/ml, 250 ml | rabat 5% |
| Eficur 250 + 100 | LHPEFI100 | Eficur 50mg/ml, 100 ml | |

- Towary jednego pakietu mają identyczną nazwę w kolumnie *Pakiet*.
- Ten sam towar może być w wielu pakietach.
- *Nazwa towaru* i *Uwagi* są opcjonalne.

Arkusz **Towary** (opcjonalny, zalecany): pełna lista kodów towarów z XL, np. wklejona z eksportu kartoteki.
Dzięki niej program pewniej odróżnia błąd odczytu od towaru spoza pakietów.

Po zapisaniu pliku program sam wczyta zmiany (lub kliknij **↻ Pakiety**). Plik może leżeć na dysku sieciowym (patrz wyżej).

## Wymagania wobec okna XL

- Lista pozycji przewinięta **maksymalnie w lewo**, tak aby widać było kolumny Lp., Towar i Nazwa.
- Kolumny w kolejności Lp. → Towar → Nazwa (standardowy układ). Jeśli macie inne nazwy kolumn, zmień je w `config.json`.
- Okno XL nie może być zminimalizowane. Najlepiej ustawić nakładkę z boku, poza listą pozycji.
- Jeśli pracujecie w XL przez pulpit zdalny (RDP), nakładkę trzeba zainstalować na tym serwerze, nie lokalnie.

## Ustawienia `config.json`

| Klucz | Znaczenie |
|---|---|
| `okno_tytul_regex` | Tytuł okna zamówienia (wyrażenie regularne) |
| `plik_pakietow` | Ścieżka do pliku pakietów |
| `interwal_s` | Co ile sekund odczytywać ekran |
| `ocr_silnik` | `auto`, `windows` lub `tesseract` |
| `skala` | Powiększenie obrazu przed OCR (więcej = dokładniej, wolniej) |
| `kolumna_lp`, `kolumna_kod`, `kolumna_nastepna` | Nagłówki kolumn listy pozycji |
| `pelny_skan_zabki` | Ile ząbków kółka na krok pełnego skanu (0 = automatycznie) |
| `debug_zapis_obrazow` | `true` zapisuje odczytywane wycinki do folderu `debug\` |

## Diagnoza problemów z odczytem

Zrób zrzut okna ZS (Win+Shift+S → zapisz jako PNG) i uruchom w folderze programu:

```bat
"%LOCALAPPDATA%\Programs\OCR-PAKIET\OCR-PAKIET.exe" --obraz zrzut.png --wynik wynik.txt
```

Program zapisze do `wynik.txt` odczytane Lp. i kody oraz pasujące pakiety. Jeśli kody są źle czytane,
zwiększ `skala` (np. do 4) albo włącz `debug_zapis_obrazow` i sprawdź wycinki w folderze `debug\`.

## Dla programisty

```
ocr_pakiet/
  app.py          okienko (tkinter) i wątek odczytu
  winutil.py      wyszukanie okna, zrzut (PrintWindow), przewijanie kółkiem
  reader.py       wykrycie nagłówka listy, przygotowanie obrazu, parsowanie Lp. + kod
  ocr_engine.py   Windows OCR (WinRT) i Tesseract
  order_state.py  składanie pozycji z wielu ekranów jednego ZS
  scanner.py      pełny skan z automatycznym przewijaniem
  packages.py     pakiety z Excela, dopasowanie kodów, podpowiedzi
tests/            testy logiki: python -m pytest tests
narzedzia/        generator szablonu pakiety_szablon.xlsx
```

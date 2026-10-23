"""Testy logiki niezależnej od Windows: python -m pytest tests"""
from ocr_pakiet.ocr_engine import Word
from ocr_pakiet.order_state import OrderState, order_key
from ocr_pakiet.packages import CodeMatcher, Item, Package, PackageBook
from ocr_pakiet.reader import ReadResult, Row, _fix_lp_sequence, parse_line


def words(*texts):
    return [Word(t, i * 50, 0, 40, 10) for i, t in enumerate(texts)]


def test_parse_line_basic():
    assert parse_line(words("00001", "LHPINMV25")) == (1, "LHPINMV25")


def test_parse_line_glued_and_border():
    assert parse_line(words("00011|L002108")) == (11, "L002108")
    assert parse_line(words("00001LHPINMV25")) == (1, "LHPINMV25")


def test_parse_line_ocr_digits_and_split_code():
    assert parse_line(words("O0O12", "LHPSELC", "100")) == (12, "LHPSELC100")


def test_parse_line_rejects_header():
    assert parse_line(words("Lp.", "Towar")) is None


def test_fix_lp_sequence_uses_position():
    rows = [Row(10, "A1X", 100), Row(11, "B1X", 118), Row(17, "C1X", 136), Row(14, "D1X", 172)]
    fixed = _fix_lp_sequence(rows)
    assert [r.lp for r in fixed] == [10, 11, 12, 14]


def test_matcher():
    m = CodeMatcher({"LHPDIVPEN5", "L002591", "LHPEFI100"}, set())
    assert m.match("LHPDIVPENS") == "LHPDIVPEN5"   # S/5
    assert m.match("LHIPDIVPENS") == "LHPDIVPEN5"  # dodatkowe I
    assert m.match("LHIPEFI100") == "LHPEFI100"
    assert m.match("L002594") is None              # inna cyfra = inny towar
    assert m.match("XYZ") is None


def test_order_state_merges_screens():
    st = OrderState()
    t = "Zamówienie sprzedaży [ZS-1/26] - edycja"
    st.apply(ReadResult(rows=[Row(i, f"K{i}", i * 18) for i in range(1, 28)], reached_end=False), t)
    assert not st.complete and len(st.rows) == 27
    st.apply(ReadResult(rows=[Row(i, f"K{i}", i * 18) for i in range(20, 35)], reached_end=True), t)
    assert st.complete and len(st.rows) == 34 and st.missing_lps() == []
    st.apply(ReadResult(rows=[Row(1, "X", 18)], reached_end=True), "Zamówienie sprzedaży [ZS-2/26]")
    assert st.key == "ZS-2/26" and st.rows == {1: "X"}


def test_order_key():
    assert order_key("Zamówienie sprzedaży [ZS-464/26/B2B/10] - edycja") == "ZS-464/26/B2B/10"


def test_suggest_order():
    book = PackageBook.__new__(PackageBook)
    book.packages = [
        Package("A", [Item("X"), Item("Y")]),
        Package("B", [Item("X"), Item("Z"), Item("W")]),
        Package("C", [Item("Q")]),
    ]
    s = PackageBook.suggest(book, {"X", "Y"})
    assert [x.package.name for x in s] == ["B", "A"]
    assert s[1].complete and [i.code for i in s[0].missing] == ["Z", "W"]


def test_package_source_fallback(tmp_path):
    import shutil

    from ocr_pakiet.packages import PackageSource

    root = __file__.rsplit("tests", 1)[0]
    shared = tmp_path / "Z" / "pakiety.xlsx"
    cache = tmp_path / "pakiety_kopia.xlsx"
    shared.parent.mkdir()
    shutil.copyfile(root + "pakiety_szablon.xlsx", shared)

    src = PackageSource(str(shared), str(cache))
    assert src.refresh(force=True) and src.ok and cache.exists()
    assert len(src.book.packages) == 3

    shared.unlink()  # dysk sieciowy niedostępny -> ostatnia kopia
    assert src.refresh(force=True) and src.ok and src.status.startswith("⚠")
    assert len(src.book.packages) == 3

    cache.unlink()
    src2 = PackageSource(str(shared), str(cache))
    assert src2.refresh(force=True) and not src2.ok and "Brak pliku" in src2.status


def test_package_source_bad_file(tmp_path):
    from openpyxl import Workbook

    from ocr_pakiet.packages import PackageSource

    p = tmp_path / "pakiety.xlsx"
    Workbook().save(p)  # pusty plik – bez kolumn
    src = PackageSource(str(p), str(tmp_path / "kopia.xlsx"))
    src.refresh(force=True)
    assert not src.ok and "Błąd" in src.status


def test_promo_badges():
    from ocr_pakiet.promo import GRATIS, INFO, MIX, RABAT, parse

    cases = {
        "7+1": ("7+1", GRATIS, False),
        "12 szt.: -25%": ("-25% od 12 szt.", RABAT, False),
        "1 szt.: -10% (do 27.11.2026)": ("-10% od 1 szt.", RABAT, False),
        "10 op.: -10% / 25 op.: -15%": ("-10% od 10 op.", RABAT, True),
        "MIX Dechra: 1500 zł netto: -7% / 3000 zł netto: -10%": ("MIX -7% od 1500 zł", MIX, True),
        "5+1 lub MIX Dechra: 1500 zł netto: -7%": ("5+1", GRATIS, True),
        "Zylkene 100 kaps. (75 / 225 / 450 mg): 2 szt.: -30%": ("-30% od 2 szt.", RABAT, True),
        "29 szt.: +1 szt. za 1 zł": ("29+1 za 1 zł", GRATIS, True),
        "48 szt.: 21 zł/szt. / 96 szt.: 19 zł/szt.": ("21 zł/szt. od 48 szt.", RABAT, True),
        "Pakiet uśredniony – indywidualne warunki u przedstawiciela": ("warunki indyw.", INFO, True),
    }
    for note, (badge, kind, detail) in cases.items():
        p = parse(note)
        assert (p.badge, p.kind, p.show_detail) == (badge, kind, detail), note
    assert parse("1 szt.: -10% (do 27.11.2026)").deadline == "27.11"


def test_new_item_only_below_known_end():
    t = "Zamówienie sprzedaży [ZS-9/26] - edycja"
    st = OrderState()
    rows = lambda a, b: [Row(i, f"K{i}", i * 18) for i in range(a, b + 1)]
    st.apply(ReadResult(rows=rows(1, 5), reached_end=True), t)
    assert st.new_lps == set()                      # pierwszy odczyt – nic nie jest „nowe”
    st.apply(ReadResult(rows=rows(1, 6), reached_end=True), t)
    assert st.new_lps == {6}                        # dodano pozycję pod końcem listy
    st.apply(ReadResult(rows=rows(1, 6), reached_end=True), t)
    assert st.new_lps == set()                      # ten sam stan – już nie nowa

    long = OrderState()
    long.apply(ReadResult(rows=rows(1, 20), reached_end=False), t)
    long.apply(ReadResult(rows=rows(15, 40), reached_end=True), t)
    assert long.new_lps == set()                    # przewinięcie – stare pozycje, koniec nieznany wcześniej
    long.apply(ReadResult(rows=rows(20, 41), reached_end=True), t)
    assert long.new_lps == {41}

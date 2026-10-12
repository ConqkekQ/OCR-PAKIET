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

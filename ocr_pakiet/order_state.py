"""Stan aktualnie otwartego zamówienia: pozycje zebrane z kolejnych ekranów.

Lista pozycji często nie mieści się na jednym ekranie. Każdy odczyt dokłada
pozycje (po numerze Lp.) do pamięci zamówienia, więc wystarczy przewinąć listę,
a nakładka "zbierze" resztę. Zamówienie rozpoznajemy po numerze ZS z tytułu okna.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .reader import ReadResult

_ZS_RE = re.compile(r"\[([^\]]+)\]")


def order_key(title: str) -> str:
    m = _ZS_RE.search(title)
    return m.group(1).strip() if m else title.strip()


@dataclass
class OrderState:
    key: str = ""
    rows: dict[int, str] = field(default_factory=dict)  # Lp -> kod z OCR
    complete: bool = False  # cała lista została przejrzana (od 1 do końca)

    def reset(self, key: str = "") -> None:
        self.key = key
        self.rows = {}
        self.complete = False

    def apply(self, res: ReadResult, title: str) -> None:
        key = order_key(title)
        if key != self.key:
            self.reset(key)
        if not res.rows:
            return
        visible = {r.lp: r.code for r in res.rows}
        lo, hi = min(visible), max(visible)
        whole_list_visible = lo == 1 and res.reached_end
        if whole_list_visible:
            # cała lista na jednym ekranie – to jest pełny, aktualny obraz zamówienia
            self.rows = dict(visible)
            self.complete = True
            return
        self.rows.update(visible)
        if res.reached_end:
            # widzimy koniec listy: wszystko poniżej ostatniego Lp. jest nieaktualne
            for lp in [lp for lp in self.rows if lp > hi]:
                del self.rows[lp]
            self.complete = self.missing_lps() == [] and 1 in self.rows
        else:
            self.complete = False

    def replace(self, rows: dict[int, str], key: str) -> None:
        self.key = key
        self.rows = dict(rows)
        self.complete = bool(rows) and not self.missing_lps() and 1 in rows

    def missing_lps(self) -> list[int]:
        if not self.rows:
            return []
        return [lp for lp in range(1, max(self.rows) + 1) if lp not in self.rows]

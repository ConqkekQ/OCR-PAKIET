"""Opis promocji -> krótka plakietka, typ (kolor) i termin.

Opisy w pliku pakietów mają ujednolicony format (arkusz „Zasady opisu”):
  [MIX <czego>:] <próg>: <korzyść> / <próg>: <korzyść> [lub <wariant>] [(do dd.mm.rrrr)]
"""
from __future__ import annotations

import re
from dataclasses import dataclass

GRATIS, RABAT, MIX, INFO = "gratis", "rabat", "mix", "info"

_TERMIN = re.compile(r"\s*\(do (\d{1,2})\.(\d{1,2})\.(\d{4})\)")


@dataclass(frozen=True)
class Promo:
    badge: str          # tekst plakietki, np. "7+1", "-25% od 12 szt."
    kind: str           # GRATIS / RABAT / MIX / INFO – decyduje o kolorze
    deadline: str       # "27.11" albo ""
    show_detail: bool   # czy pełny opis wnosi coś ponad plakietkę


def parse(note: str) -> Promo:
    note = (note or "").strip()
    if not note:
        return Promo("pakiet", INFO, "", False)
    m = _TERMIN.search(note)
    deadline = f"{int(m.group(1)):02d}.{int(m.group(2)):02d}" if m else ""
    core = _TERMIN.sub("", note).strip()

    variant = _split(core, " lub ")[0]
    is_mix = variant.upper().startswith("MIX")
    body = re.sub(r"^MIX\b[^:]*?:\s*", "", variant, flags=re.I) if is_mix else variant
    body = re.sub(r"^MIX\s+", "", body, flags=re.I)
    first = _split(body, " / ")[0].strip()
    # opis zakresu przed progiem, np. „Zylkene 100 kaps. (75 / 225 / 450 mg): 2 szt.: -30%”
    if first.count(":") >= 2 and not re.match(r"^[\d–\-]", first):
        first = first.split(":", 1)[1].strip()

    if mm := re.match(r"^(\d+\+\d+)", first):
        badge, kind = mm.group(1), GRATIS
    elif mm := re.match(r"^[^:]+:\s*(\d+\+\d+)", first):
        badge, kind = mm.group(1), GRATIS
    elif mm := re.match(r"^(\d+) \S+:\s*\+(\d+) \S+ za 1 zł", first):
        badge, kind = f"{mm.group(1)}+{mm.group(2)} za 1 zł", GRATIS
    elif mm := re.match(r"^([\d ]+zł)(?: netto)?[^:]*:\s*-(\d+%)", first):
        badge, kind = f"-{mm.group(2)} od {mm.group(1).strip()}", RABAT
    elif mm := re.match(r"^([\d–\-]+ ?[^\s:]*)[^:]*:\s*-(\d+%)", first):
        badge, kind = f"-{mm.group(2)} od {mm.group(1).strip()}", RABAT
    elif mm := re.match(r"^([\d ]+zł)(?: netto)?[^:]*:\s*gratis", first):
        badge, kind = f"gratis od {mm.group(1).strip()}", GRATIS
    elif mm := re.match(r"^([\d–\-]+ ?[^\s:(]*)[^:]*:\s*.*gratis", first):
        badge, kind = f"gratis od {mm.group(1).strip()}", GRATIS
    elif mm := re.match(r"^([\d]+ \S+):\s*([\d,]+ zł/\S+)", first):
        badge, kind = f"{mm.group(2)} od {mm.group(1)}", RABAT
    elif mm := re.match(r"^([\d]+ \S+):\s*([\d,]+ zł)(?: netto)?\b", first):
        badge, kind = f"{mm.group(1)} za {mm.group(2)}", RABAT
    elif "u przedstawiciela" in first or "indywidualn" in first:
        badge, kind = "warunki indyw.", INFO
    elif mm := re.search(r"-\d+%", first):
        badge, kind = mm.group(0) + "…", RABAT
    else:
        badge, kind = (first[:20] + "…") if len(first) > 21 else first, RABAT
    if is_mix:
        badge, kind = f"MIX {badge}", MIX

    simple = re.fullmatch(r"\d+\+\d+|[\d–\-]+ \S+: -\d+%", core) is not None
    return Promo(badge, kind, deadline, not simple)


def _split(text: str, sep: str) -> list[str]:
    """Dzieli tekst po separatorze, ale nie wewnątrz nawiasów."""
    parts, depth, cur, i = [], 0, "", 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and text.startswith(sep, i):
            parts.append(cur)
            cur, i = "", i + len(sep)
            continue
        cur += ch
        i += 1
    parts.append(cur)
    return parts

"""Riconoscimento di date e importi in formato italiano."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# 1.234,56  |  1234,56  |  -1.234,56  |  1.234,56-  |  € 1.234,56
RE_IMPORTO = re.compile(
    r"^(?P<pre>[-+])?\s*(?:€\s*)?(?P<num>\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})\s*(?:€)?(?P<post>[-+])?$"
)
RE_IMPORTO_INLINE = re.compile(
    r"(?<![\d,])[-+]?\s?(?:€\s*)?(?:\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?:\s?€)?[-+]?(?![\d,])"
)

RE_DATA = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$")
RE_DATA_INLINE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")

MESI = {
    "gen": 1, "gennaio": 1, "feb": 2, "febbraio": 2, "mar": 3, "marzo": 3,
    "apr": 4, "aprile": 4, "mag": 5, "maggio": 5, "giu": 6, "giugno": 6,
    "lug": 7, "luglio": 7, "ago": 8, "agosto": 8, "set": 9, "settembre": 9,
    "ott": 10, "ottobre": 10, "nov": 11, "novembre": 11, "dic": 12, "dicembre": 12,
}
RE_DATA_TESTUALE = re.compile(
    r"^(\d{1,2})\s+(" + "|".join(sorted(MESI, key=len, reverse=True)) + r")\.?\s+(\d{4})$",
    re.IGNORECASE,
)


def parse_importo(tok: str) -> Optional[Decimal]:
    """'1.234,56' -> Decimal('1234.56'); '1.234,56-' -> -1234.56. None se non è un importo."""
    m = RE_IMPORTO.match(tok.strip())
    if not m:
        return None
    num = m.group("num").replace(".", "").replace(",", ".")
    try:
        val = Decimal(num)
    except InvalidOperation:
        return None
    if m.group("pre") == "-" or m.group("post") == "-":
        val = -val
    return val


RE_IMPORTO_LASCO = re.compile(r"(?<![\d,.])([-+])?\s*(\d{1,3}(?:[.\s\x19\u00a0]{1,2}\d{3})+|\d+),\s?(\d{2})(?![\d,])")


def importi_in_testo(testo: str) -> list[Decimal]:
    """Trova gli importi in una riga di testo in modo tollerante: '+1 917, 16 €' -> 1917.16.
    Serve per le righe di saldo/riepilogo, dove alcune banche spezzano le cifre."""
    out: list[Decimal] = []
    for m in RE_IMPORTO_LASCO.finditer(testo):
        segno, intero, cent = m.groups()
        intero = re.sub(r"[\s.\x19 ]", "", intero)
        if not intero.isdigit():
            continue
        try:
            v = Decimal(f"{intero}.{cent}")
        except InvalidOperation:
            continue
        out.append(-v if segno == "-" else v)
    return out


def parse_data(tok: str, anno_default: Optional[int] = None) -> Optional[date]:
    tok = tok.strip()
    m = RE_DATA.match(tok)
    if m:
        g, me, a = (int(x) for x in m.groups())
        if a < 100:
            a += 2000
        try:
            return date(a, me, g)
        except ValueError:
            return None
    m = RE_DATA_TESTUALE.match(tok)
    if m:
        g, mese, a = m.groups()
        try:
            return date(int(a), MESI[mese.lower()], int(g))
        except ValueError:
            return None
    # formato gg/mm senza anno (alcune banche lo usano nella colonna valuta)
    m = re.match(r"^(\d{1,2})[/.\-](\d{1,2})$", tok)
    if m and anno_default:
        try:
            return date(anno_default, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def is_data(tok: str) -> bool:
    return parse_data(tok, anno_default=2000) is not None


def is_importo(tok: str) -> bool:
    return parse_importo(tok) is not None


def formatta_importo(v: Decimal) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s

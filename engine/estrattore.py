"""Estrazione parole con coordinate da un PDF.

Motore principale: pypdfium2 (PDFium, C++): ~40x più veloce di pdfminer.
Riserva: pdfplumber, se pypdfium2 non è disponibile o fallisce.

Ogni parola è un dict con le stesse chiavi di pdfplumber.extract_words:
  text, x0, x1, top, bottom   (top/bottom misurati dall'alto della pagina)
"""
from __future__ import annotations

from typing import Iterator

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover
    pdfium = None


# spazi tipografici e caratteri di controllo che separano le parole
SEPARATORI = frozenset("\r\n\t \u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000\x19\ufeff\u200b")


def _parole_pagina_pdfium(page) -> list[dict]:
    tp = page.get_textpage()
    n = tp.count_chars()
    h = page.get_height()
    testo = tp.get_text_range(0, n) if n else ""
    # get_text_range può normalizzare i caratteri di controllo: lavoriamo carattere per carattere
    parole: list[dict] = []
    corrente: list[tuple[str, float, float, float, float]] = []

    def chiudi():
        if not corrente:
            return
        text = "".join(c[0] for c in corrente)
        if text.strip():
            x0 = min(c[1] for c in corrente)
            x1 = max(c[2] for c in corrente)
            top = min(c[3] for c in corrente)
            bottom = max(c[4] for c in corrente)
            parole.append({"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom})
        corrente.clear()

    prev_x1 = None
    prev_top = None
    for i in range(n):
        ch = testo[i] if i < len(testo) else tp.get_text_range(i, 1)
        if ch in SEPARATORI or ch.isspace():
            chiudi()
            prev_x1 = None
            continue
        l, b, r, t = tp.get_charbox(i, loose=True)
        if r - l <= 0 and t - b <= 0:
            continue
        top = h - t
        bottom = h - b
        altezza = max(bottom - top, 1.0)
        # nuova parola se c'è un salto orizzontale (> 1/4 dell'altezza del carattere) o verticale
        if prev_x1 is not None and (l - prev_x1 > altezza * 0.25 or l < prev_x1 - altezza or abs(top - prev_top) > altezza * 0.6):
            chiudi()
        corrente.append((ch, l, r, top, bottom))
        prev_x1 = r
        prev_top = top
    chiudi()
    parole.sort(key=lambda w: (round(w["top"]), w["x0"]))
    return parole


def pagine_parole(percorso: str) -> Iterator[tuple[list[dict], str]]:
    """Per ogni pagina restituisce (parole, testo_semplice)."""
    if pdfium is not None:
        try:
            pdf = pdfium.PdfDocument(percorso)
            try:
                for page in pdf:
                    parole = _parole_pagina_pdfium(page)
                    yield parole, _testo_da_parole(parole)
                return
            finally:
                pdf.close()
        except Exception:  # noqa: BLE001 — si ricade su pdfplumber
            pass
    import pdfplumber
    with pdfplumber.open(percorso) as pdf:
        for page in pdf:
            parole = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
            yield parole, (page.extract_text() or "")


def _testo_da_parole(parole: list[dict], tol: float = 3.0) -> str:
    righe: list[str] = []
    corrente: list[str] = []
    top_corr = None
    for w in parole:
        if top_corr is None or abs(w["top"] - top_corr) <= tol:
            corrente.append(w["text"])
            top_corr = w["top"] if top_corr is None else top_corr
        else:
            righe.append(" ".join(corrente))
            corrente = [w["text"]]
            top_corr = w["top"]
    if corrente:
        righe.append(" ".join(corrente))
    return "\n".join(righe)

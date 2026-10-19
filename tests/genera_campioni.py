"""Genera estratti conto PDF sintetici in tre layout diversi, con saldi coerenti.

Servono per testare il parser finché non abbiamo PDF reali (anonimizzati).
Uso:  python -m tests.genera_campioni
"""
from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engine.numeri import formatta_importo

OUT = os.path.join(os.path.dirname(__file__), "samples")
random.seed(7)

MOVIMENTI_BASE = [
    ("Pagamento POS Esselunga Gallarate", Decimal("-84.30")),
    ("Bonifico a vostro favore da ROSSI MARIO stipendio settembre", Decimal("2150.00")),
    ("Addebito SDD Enel Energia bolletta luce", Decimal("-96.45")),
    ("Prelievo ATM Banca filiale 0231", Decimal("-200.00")),
    ("Pagamento POS Farmacia Comunale", Decimal("-23.90")),
    ("Bonifico disposto a favore di Condominio Via Roma 12 spese condominiali", Decimal("-310.00")),
    ("Addebito carta Netflix.com", Decimal("-17.99")),
    ("Pagamento F24 Agenzia Entrate", Decimal("-452.12")),
    ("Pagamento POS Q8 carburante", Decimal("-65.00")),
    ("Accredito rimborso Amazon EU", Decimal("34.50")),
    ("Commissioni e spese tenuta conto", Decimal("-4.00")),
    ("Pagamento POS Trenitalia", Decimal("-28.60")),
    ("Addebito SDD Fastweb", Decimal("-29.95")),
    ("Bonifico a vostro favore da PAROLE INSIEME SRLS compenso", Decimal("850.00")),
    ("Pagamento POS Decathlon", Decimal("-49.99")),
    ("Imposta di bollo", Decimal("-8.55")),
]


def _dati(saldo_iniziale: Decimal, mese: int = 9, anno: int = 2025):
    movs = []
    g = date(anno, mese, 1)
    for desc, imp in MOVIMENTI_BASE:
        g += timedelta(days=random.randint(0, 3))
        movs.append((g, g + timedelta(days=random.choice([0, 1, 2])), desc, imp))
    finale = saldo_iniziale + sum(m[3] for m in movs)
    return movs, finale


def _spezza(testo: str, n: int) -> tuple[str, str]:
    """Spezza a fine parola, come fanno gli estratti conto reali."""
    if len(testo) <= n:
        return testo, ""
    taglio = testo.rfind(" ", 0, n)
    return testo[:taglio], testo[taglio + 1:]


def _intestazione(c, banca: str, y: float) -> float:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, banca)
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 14, "Estratto conto corrente n. 1234567 - Intestatario: MARIO ROSSI")
    c.drawString(40, y - 26, "IBAN IT60X0542811101000000123456 - Periodo: 01/09/2025 - 30/09/2025")
    return y - 50


def layout_dare_avere(path: str):
    """Layout classico: Data | Valuta | Descrizione | Dare | Avere."""
    saldo_in = Decimal("1523.40")
    movs, saldo_fin = _dati(saldo_in)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = _intestazione(c, "INTESA SANPAOLO S.p.A.", h - 50)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Data"); c.drawString(90, y, "Valuta"); c.drawString(145, y, "Descrizione operazione")
    c.drawRightString(460, y, "Dare"); c.drawRightString(540, y, "Avere")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(145, y, "Saldo iniziale"); c.drawRightString(540, y, formatta_importo(saldo_in)); y -= 14
    for d, dv, desc, imp in movs:
        if y < 80:
            c.showPage(); y = h - 50; c.setFont("Helvetica", 9)
        c.drawString(40, y, d.strftime("%d/%m/%Y")); c.drawString(90, y, dv.strftime("%d/%m/%Y"))
        prima, resto = _spezza(desc, 52)
        c.drawString(145, y, prima)
        if imp < 0:
            c.drawRightString(460, y, formatta_importo(-imp))
        else:
            c.drawRightString(540, y, formatta_importo(imp))
        y -= 13
        if resto:
            c.drawString(145, y, resto); y -= 13
    y -= 6
    c.setFont("Helvetica-Bold", 9)
    c.drawString(145, y, "Saldo finale al 30/09/2025"); c.drawRightString(540, y, formatta_importo(saldo_fin))
    c.save()
    return movs, saldo_in, saldo_fin


def layout_importo_segno(path: str):
    """Layout moderno: Data | Descrizione | Importo (con segno) — stile banche online."""
    saldo_in = Decimal("412.07")
    movs, saldo_fin = _dati(saldo_in)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = _intestazione(c, "FinecoBank", h - 50)
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "Saldo precedente al 31/08/2025:"); c.drawString(220, y, formatta_importo(saldo_in) + " €"); y -= 20
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Data contabile"); c.drawString(120, y, "Descrizione"); c.drawRightString(540, y, "Importo")
    y -= 14
    c.setFont("Helvetica", 9)
    for d, dv, desc, imp in movs:
        c.drawString(40, y, d.strftime("%d.%m.%Y"))
        c.drawString(120, y, desc[:60])
        c.drawRightString(540, y, ("-" if imp < 0 else "+") + formatta_importo(abs(imp)) + " €")
        y -= 13
    y -= 8
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Nuovo saldo al 30/09/2025:"); c.drawString(220, y, formatta_importo(saldo_fin) + " €")
    c.save()
    return movs, saldo_in, saldo_fin


def layout_con_saldo_progressivo(path: str):
    """Layout con colonna Saldo progressivo: Data | Descrizione | Uscite | Entrate | Saldo."""
    saldo_in = Decimal("3001.00")
    movs, saldo_fin = _dati(saldo_in)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    y = _intestazione(c, "UniCredit S.p.A.", h - 50)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Data"); c.drawString(95, y, "Descrizione")
    c.drawRightString(400, y, "Uscite"); c.drawRightString(470, y, "Entrate"); c.drawRightString(545, y, "Saldo")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(95, y, "Saldo contabile iniziale"); c.drawRightString(545, y, formatta_importo(saldo_in)); y -= 13
    saldo = saldo_in
    for d, dv, desc, imp in movs:
        saldo += imp
        c.drawString(40, y, d.strftime("%d/%m/%y")); c.drawString(95, y, desc[:48])
        if imp < 0:
            c.drawRightString(400, y, formatta_importo(-imp))
        else:
            c.drawRightString(470, y, formatta_importo(imp))
        c.drawRightString(545, y, formatta_importo(saldo))
        y -= 13
    y -= 6
    c.setFont("Helvetica-Bold", 9)
    c.drawString(95, y, "Saldo contabile finale"); c.drawRightString(545, y, formatta_importo(saldo_fin))
    c.save()
    return movs, saldo_in, saldo_fin


def main():
    os.makedirs(OUT, exist_ok=True)
    attese = {}
    for nome, fn in (
        ("dare_avere.pdf", layout_dare_avere),
        ("importo_segno.pdf", layout_importo_segno),
        ("saldo_progressivo.pdf", layout_con_saldo_progressivo),
    ):
        movs, si, sf = fn(os.path.join(OUT, nome))
        attese[nome] = {
            "saldo_iniziale": str(si), "saldo_finale": str(sf), "n": len(movs),
            "importi": [str(m[3]) for m in movs],
        }
        print("generato", nome)
    with open(os.path.join(OUT, "attese.json"), "w") as f:
        json.dump(attese, f, indent=2)


if __name__ == "__main__":
    main()

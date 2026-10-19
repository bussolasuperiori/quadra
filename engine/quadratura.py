"""Controllo di quadratura: saldo iniziale + movimenti = saldo finale."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .models import Movimento, Quadratura
from .numeri import formatta_importo


def calcola_quadratura(
    saldo_iniziale: Optional[Decimal],
    saldo_finale: Optional[Decimal],
    movimenti: list[Movimento],
) -> Quadratura:
    totale = sum((m.importo for m in movimenti), Decimal("0"))
    if saldo_iniziale is None or saldo_finale is None:
        return Quadratura(
            saldo_iniziale=saldo_iniziale,
            saldo_finale=saldo_finale,
            totale_movimenti=totale,
            saldo_calcolato=None,
            differenza=None,
            quadra=None,
            messaggio="Saldi non trovati nel PDF: impossibile verificare la quadratura. Controlla i totali manualmente.",
        )
    calcolato = saldo_iniziale + totale
    diff = (saldo_finale - calcolato).quantize(Decimal("0.01"))
    if diff == 0:
        msg = f"I conti tornano: {len(movimenti)} movimenti, saldo finale {formatta_importo(saldo_finale)} €."
    else:
        msg = (
            f"Attenzione: differenza di {formatta_importo(diff)} € tra saldo finale dichiarato "
            f"({formatta_importo(saldo_finale)} €) e saldo ricalcolato ({formatta_importo(calcolato)} €). "
            "Potrebbe mancare un movimento o un segno potrebbe essere invertito."
        )
    return Quadratura(
        saldo_iniziale=saldo_iniziale,
        saldo_finale=saldo_finale,
        totale_movimenti=totale,
        saldo_calcolato=calcolato,
        differenza=diff,
        quadra=(diff == 0),
        messaggio=msg,
    )

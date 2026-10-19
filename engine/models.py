"""Modelli dati del motore Quadra."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Movimento:
    data: date
    descrizione: str
    importo: Decimal                 # negativo = uscita, positivo = entrata
    data_valuta: Optional[date] = None
    categoria: str = "Altro"
    riga_origine: int = 0            # riga del testo da cui è stato estratto (debug)

    def to_dict(self) -> dict:
        return {
            "data": self.data.isoformat(),
            "data_valuta": self.data_valuta.isoformat() if self.data_valuta else None,
            "descrizione": self.descrizione,
            "importo": float(self.importo),
            "categoria": self.categoria,
        }


@dataclass
class Quadratura:
    saldo_iniziale: Optional[Decimal]
    saldo_finale: Optional[Decimal]
    totale_movimenti: Decimal
    saldo_calcolato: Optional[Decimal]
    differenza: Optional[Decimal]
    quadra: Optional[bool]           # None = saldi non trovati nel PDF
    messaggio: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


@dataclass
class Risultato:
    banca: str
    metodo: str                      # "template:<banca>" | "generico"
    movimenti: list[Movimento] = field(default_factory=list)
    quadratura: Optional[Quadratura] = None
    avvisi: list[str] = field(default_factory=list)
    pagine: int = 0

    @property
    def entrate(self) -> Decimal:
        return sum((m.importo for m in self.movimenti if m.importo > 0), Decimal("0"))

    @property
    def uscite(self) -> Decimal:
        return sum((m.importo for m in self.movimenti if m.importo < 0), Decimal("0"))

    def to_dict(self) -> dict:
        return {
            "banca": self.banca,
            "metodo": self.metodo,
            "pagine": self.pagine,
            "n_movimenti": len(self.movimenti),
            "entrate": float(self.entrate),
            "uscite": float(self.uscite),
            "movimenti": [m.to_dict() for m in self.movimenti],
            "quadratura": self.quadratura.to_dict() if self.quadratura else None,
            "avvisi": self.avvisi,
        }

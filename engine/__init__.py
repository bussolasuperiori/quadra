"""Quadra — motore di conversione estratti conto PDF → movimenti strutturati."""
from .parser import analizza_pdf
from .categorie import categorizza
from .export import to_csv, to_xlsx
from .models import Risultato, Movimento, Quadratura


def converti(percorso_pdf: str) -> Risultato:
    """Pipeline completa: parsing + categorie + quadratura."""
    ris = analizza_pdf(percorso_pdf)
    categorizza(ris.movimenti)
    return ris


__all__ = ["converti", "analizza_pdf", "categorizza", "to_csv", "to_xlsx", "Risultato", "Movimento", "Quadratura"]

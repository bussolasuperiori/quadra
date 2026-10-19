"""Registro dei template per banca.

Un template è un modulo con due funzioni:
  riconosce(doc) -> bool      il documento è di questa banca/layout?
  parse(doc) -> Risultato     parsing specifico
Se il template non produce movimenti, si ricade sul parser generico.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import trade_republic

TEMPLATES = [trade_republic]


def template_per(doc) -> Optional[Callable]:
    for t in TEMPLATES:
        try:
            if t.riconosce(doc):
                return t.parse
        except Exception:  # noqa: BLE001
            continue
    return None

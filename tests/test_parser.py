"""Test end-to-end del motore sui campioni sintetici.  Uso: python -m tests.test_parser"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

from engine import converti, to_csv, to_xlsx

SAMPLES = os.path.join(os.path.dirname(__file__), "samples")


def main() -> int:
    with open(os.path.join(SAMPLES, "attese.json")) as f:
        attese = json.load(f)
    errori = 0
    for nome, att in attese.items():
        ris = converti(os.path.join(SAMPLES, nome))
        q = ris.quadratura
        ok_n = len(ris.movimenti) == att["n"]
        ok_imp = [str(m.importo) for m in ris.movimenti] == att["importi"]
        ok_q = bool(q and q.quadra)
        ok_saldi = q and str(q.saldo_iniziale) == att["saldo_iniziale"] and str(q.saldo_finale) == att["saldo_finale"]
        stato = "OK " if (ok_n and ok_imp and ok_q and ok_saldi) else "ERR"
        if stato == "ERR":
            errori += 1
        print(f"[{stato}] {nome:24s} banca={ris.banca:16s} metodo={ris.metodo:18s} "
              f"movimenti={len(ris.movimenti)}/{att['n']} quadra={q.quadra if q else None}")
        if not ok_imp:
            for m in ris.movimenti:
                print("      ", m.data, f"{m.importo:>10}", m.categoria[:22].ljust(22), m.descrizione[:60])
        if not ok_saldi and q:
            print("       saldi letti:", q.saldo_iniziale, q.saldo_finale, "attesi:", att["saldo_iniziale"], att["saldo_finale"])
        for a in ris.avvisi:
            print("       avviso:", a)
        # export non deve esplodere
        to_csv(ris)
        xlsx = to_xlsx(ris)
        assert len(xlsx) > 1000
    # categorie: stampa un campione
    ris = converti(os.path.join(SAMPLES, "dare_avere.pdf"))
    print("\nCategorie assegnate (dare_avere.pdf):")
    for m in ris.movimenti:
        print(f"   {m.importo:>9}  {m.categoria:30s} {m.descrizione[:50]}")
    print("\nLayout reali:")
    errori += test_reali()
    print("\nTOTALE ERRORI:", errori)
    return 1 if errori else 0


# ---------------------------------------------------------------------------
# Layout reali (PDF anonimizzati con tests/anonimizza.py): devono quadrare
# ---------------------------------------------------------------------------
REALI = {
    "reale_intesa_xme.pdf": {"banca": "Intesa Sanpaolo", "n": 196},
    "reale_trade_republic.pdf": {"banca": "Trade Republic", "n": 15},
}


def test_reali() -> int:
    errori = 0
    for nome, att in REALI.items():
        p = os.path.join(SAMPLES, nome)
        if not os.path.exists(p):
            print(f"[SKIP] {nome} non presente")
            continue
        ris = converti(p)
        q = ris.quadratura
        ok = ris.banca == att["banca"] and len(ris.movimenti) == att["n"] and bool(q and q.quadra)
        errori += 0 if ok else 1
        print(f"[{'OK ' if ok else 'ERR'}] {nome:26s} banca={ris.banca:16s} metodo={ris.metodo:24s} "
              f"movimenti={len(ris.movimenti)}/{att['n']} quadra={q.quadra if q else None}")
    return errori


if __name__ == "__main__":
    sys.exit(main())

"""Template Trade Republic (estratto conto "riassuntivo").

Particolarità del layout:
- la data è spezzata: "16 set" sulla prima riga del blocco, "2026" sull'ultima;
- colonne IN ENTRATA | IN USCITA | SALDO, importi allineati a destra con " €";
- l'importo può stare sulla prima o sulla seconda riga del blocco;
- la colonna TIPO (Interessi, Bonifico, Commercio, Rendimento) precede la descrizione;
- il riepilogo iniziale riporta: Conto corrente <saldo iniziale> <entrate> <uscite> <saldo finale>.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Optional

from ..models import Movimento, Risultato
from ..numeri import MESI, parse_importo
from ..quadratura import calcola_quadratura

RE_GIORNO = re.compile(r"^\d{1,2}$")
RE_ANNO = re.compile(r"^(20\d{2})$")


def riconosce(doc) -> bool:
    return doc.banca == "Trade Republic"


def _bordi_colonne(righe):
    """Trova la riga 'DATA TIPO DESCRIZIONE IN ENTRATA IN USCITA SALDO' e restituisce i bordi destri."""
    for r in righe:
        t = [w["text"].upper() for w in r.parole]
        if "ENTRATA" in t and "USCITA" in t and "SALDO" in t and "DATA" in t and "DESCRIZIONE" in t:
            bordi = {}
            for w in r.parole:
                u = w["text"].upper()
                if u == "ENTRATA": bordi["entrata"] = w["x1"]
                elif u == "USCITA": bordi["uscita"] = w["x1"]
                elif u == "SALDO": bordi["saldo"] = w["x1"]
            return bordi
    return None


def _colonna(x1: float, bordi: dict) -> Optional[str]:
    nome, dist = min(((n, abs(x1 - b)) for n, b in bordi.items()), key=lambda c: c[1])
    return nome if dist < 45 else None


def parse(doc) -> Risultato:
    ris = Risultato(banca="Trade Republic", metodo="template:trade_republic", pagine=doc.pagine)
    righe = doc.righe
    bordi = _bordi_colonne(righe)
    if not bordi:
        return ris

    # anno del periodo, dall'intestazione "DATA 01 set 2026 - 18 ott 2026"
    anno_periodo = None
    m = re.search(r"\b(\d{1,2})\s+([a-z]{3})\s+(20\d{2})\s*-\s*(\d{1,2})\s+([a-z]{3})\s+(20\d{2})", doc.testo, re.I)
    if m:
        anno_periodo = int(m.group(6))

    movimenti: list[Movimento] = []
    blocco = None  # dict: giorno, mese, desc(list), entrata, uscita, saldo

    def chiudi(anno: Optional[int]):
        nonlocal blocco
        if not blocco:
            return
        a = anno or anno_periodo or date.today().year
        try:
            d = date(a, blocco["mese"], blocco["giorno"])
        except ValueError:
            blocco = None
            return
        valore = None
        if blocco["entrata"] is not None:
            valore = abs(blocco["entrata"])
        elif blocco["uscita"] is not None:
            valore = -abs(blocco["uscita"])
        if valore is not None:
            desc = " ".join(blocco["desc"])
            desc = re.sub(r"\s{2,}", " ", desc).strip()
            movimenti.append(Movimento(data=d, descrizione=desc, importo=valore, riga_origine=blocco["riga"]))
            if blocco["saldo"] is not None:
                movimenti[-1].saldo_progressivo = blocco["saldo"]  # attributo extra, usato per i saldi
        blocco = None

    in_tabella = False
    for r in righe:
        toks = r.parole
        testo_up = r.testo.upper()
        if "ENTRATA" in testo_up and "USCITA" in testo_up and "SALDO" in testo_up and "DATA" in testo_up and "DESCRIZIONE" in testo_up:
            in_tabella = True
            continue
        if testo_up.startswith("PANORAMICA") or (testo_up.startswith("DATA") and "DESCRIZIONE" not in testo_up):
            chiudi(None)
            in_tabella = False
            continue
        if not in_tabella:
            continue
        if re.match(r"^(trade republic bank|generato il|pagina)", r.testo, re.I):
            continue
        primo = toks[0]
        # inizio blocco: "16 set"
        if primo["x0"] < 95 and RE_GIORNO.match(primo["text"]) and len(toks) > 1 and toks[1]["text"].lower()[:3] in MESI:
            chiudi(None)
            blocco = {"giorno": int(primo["text"]), "mese": MESI[toks[1]["text"].lower()[:3]], "desc": [],
                      "entrata": None, "uscita": None, "saldo": None, "riga": r.idx}
            resto = toks[2:]
        elif primo["x0"] < 95 and RE_ANNO.match(primo["text"]):
            # fine blocco: l'anno, eventualmente seguito da altra descrizione
            anno = int(primo["text"])
            resto = toks[1:]
            if blocco:
                _assorbi(blocco, resto, bordi)
                chiudi(anno)
            continue
        else:
            resto = toks
        if blocco is None:
            continue
        _assorbi(blocco, resto, bordi)
    chiudi(None)

    ris.movimenti = movimenti

    # saldi: dal riepilogo "Conto corrente  a  b  c  d", altrimenti dal saldo progressivo
    iniz = fin = None
    for r in righe:
        if r.testo.lower().startswith("conto corrente"):
            imp = [parse_importo(w["text"]) for w in r.parole]
            imp = [v for v in imp if v is not None]
            if len(imp) >= 4:
                iniz, fin = imp[0], imp[-1]
                break
    if (iniz is None or fin is None) and movimenti:
        saldi = [getattr(m, "saldo_progressivo", None) for m in movimenti]
        if saldi[0] is not None:
            iniz = saldi[0] - movimenti[0].importo
        if saldi[-1] is not None:
            fin = saldi[-1]
    ris.quadratura = calcola_quadratura(iniz, fin, movimenti)
    if iniz is None or fin is None:
        ris.avvisi.append("Saldi non trovati nel riepilogo Trade Republic.")
    return ris


def _assorbi(blocco: dict, toks: list[dict], bordi: dict) -> None:
    for w in toks:
        t = w["text"]
        if t == "€":
            continue
        tt = t.replace("€", "")
        v = parse_importo(tt)
        if v is not None and w["x0"] > 380:
            col = _colonna(w["x1"] if t == tt else w["x1"] - 6, bordi)
            if col == "entrata" and blocco["entrata"] is None:
                blocco["entrata"] = v; continue
            if col == "uscita" and blocco["uscita"] is None:
                blocco["uscita"] = v; continue
            if col == "saldo":
                blocco["saldo"] = v; continue
        if w["x0"] >= 95:
            blocco["desc"].append(t)

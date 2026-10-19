"""Parser di estratti conto bancari italiani (PDF testuali).

Architettura:
- `estrai_righe()` legge il PDF (pypdfium2, riserva pdfplumber) e raggruppa le parole in righe con coordinate.
- Un *template di banca* (engine/banche/) può prendere in carico il documento se lo riconosce.
- Altrimenti lavora il parser generico (`parse_generico`), che:
  1. cerca l'intestazione della tabella per conoscere le colonne Dare/Avere/Saldo;
  2. tratta come movimento ogni riga che inizia con una data e ha un importo in una
     colonna nota (o, senza colonne, qualunque importo);
  3. accoda alle descrizioni le righe senza data che seguono (anche se contengono
     sotto-importi fuori dalle colonne, es. "QUOTA CAPITALE 247,09");
  4. completa un movimento "in sospeso" (data senza importo) con l'importo che
     compare nella riga successiva.
- Saldo iniziale/finale vengono cercati con regex tolleranti su tutto il testo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from .estrattore import pagine_parole

from .models import Movimento, Risultato
from .numeri import parse_data, parse_importo, is_data, is_importo, importi_in_testo
from .quadratura import calcola_quadratura

# ---------------------------------------------------------------------------
# Riconoscimento banca
# ---------------------------------------------------------------------------
BANCHE = [
    ("Intesa Sanpaolo", r"intesa\s*sanpaolo"),
    ("Trade Republic", r"trade\s*republic"),
    ("UniCredit", r"unicredit"),
    ("BancoPosta", r"bancoposta|poste\s*italiane"),
    ("Fineco", r"fineco"),
    ("BPER", r"\bbper\b"),
    ("Banco BPM", r"banco\s*bpm"),
    ("ING", r"\bing\s*bank|\bing\b"),
    ("Revolut", r"revolut"),
    ("N26", r"\bn26\b"),
    ("Hype", r"\bhype\b"),
    ("Mediolanum", r"mediolanum"),
    ("Credit Agricole", r"cr[eé]dit\s*agricole"),
    ("MPS", r"monte\s*dei\s*paschi|\bmps\b"),
    ("Banca Sella", r"banca\s*sella"),
    ("Credem", r"\bcredem\b|credito\s*emiliano"),
    ("Widiba", r"widiba"),
    ("Illimity", r"illimity"),
    ("BCC", r"\bbcc\b|credito\s*cooperativo"),
]

# ---------------------------------------------------------------------------
# Intestazioni colonne (per prefisso: tollera "Addebi ti", "IN ENTRATA", ecc.)
# ---------------------------------------------------------------------------
PREF_DARE = ("dare", "uscit", "addeb", "debit", "pagament", "preliev")
PREF_AVERE = ("avere", "entrat", "accred", "credit", "versament", "incass")
PREF_SALDO = ("saldo",)
PREF_IMPORTO = ("importo", "importi", "ammontare")
PAROLE_TABELLA = {"data", "contabile", "valuta", "operazione", "descrizione", "causale", "tipo", "dettaglio", "movimento", "movimenti"}

RE_SALDO_INIZIALE = re.compile(
    r"saldo\s+(?:iniziale|precedente|contabile\s+iniziale|di\s+apertura|riportato|a\s+riporto|al\s+\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\s*precedente)",
    re.IGNORECASE,
)
RE_SALDO_FINALE = re.compile(
    r"(?:saldo\s+(?:finale|contabile\s+finale|di\s+chiusura|a\s+nuovo|disponibile\s+finale)|nuovo\s+saldo)",
    re.IGNORECASE,
)
RE_SALDO_FINALE_DEBOLE = re.compile(r"saldo\s+contabile(?!\s+iniziale)", re.IGNORECASE)
RE_RIGA_SERVIZIO = re.compile(
    r"^(pagina|pag\.|totale|riepilogo|estratto\s+conto|c/c\s+n|iban|filiale|al\s+\d{1,2}[./]\d{1,2}[./]\d{2,4}$|data\s+operazione|generato\s+il|segue\b|riporto\b|trasporto\b)",
    re.IGNORECASE,
)


@dataclass
class Riga:
    testo: str
    parole: list[dict]
    top: float
    pagina: int
    idx: int


@dataclass
class Colonne:
    dare: Optional[float] = None
    avere: Optional[float] = None
    saldo: Optional[float] = None
    importo: Optional[float] = None
    tolleranza: float = 60.0

    @property
    def note(self) -> bool:
        return any(v is not None for v in (self.dare, self.avere, self.importo))

    def colonna_di(self, x_centro: float) -> Optional[str]:
        cand = [(n, abs(x_centro - v)) for n, v in
                (("dare", self.dare), ("avere", self.avere), ("saldo", self.saldo), ("importo", self.importo))
                if v is not None]
        if not cand:
            return None
        nome, dist = min(cand, key=lambda c: c[1])
        return nome if dist < self.tolleranza else None


@dataclass
class Documento:
    righe: list[Riga]
    testo: str
    pagine: int
    banca: str


# ---------------------------------------------------------------------------
# Estrazione righe
# ---------------------------------------------------------------------------
def _crea_riga(parole: list[dict], pagina: int, idx: int) -> Riga:
    parole = sorted(parole, key=lambda w: w["x0"])
    return Riga(" ".join(w["text"] for w in parole), parole, parole[0]["top"], pagina, idx)


def _righe_pagina(words: list[dict], pagina_idx: int, start_idx: int, tol: float = 3.0) -> list[Riga]:
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    righe: list[Riga] = []
    corrente: list[dict] = []
    top_corr: Optional[float] = None
    for w in words:
        if top_corr is None or abs(w["top"] - top_corr) <= tol:
            corrente.append(w)
            top_corr = w["top"] if top_corr is None else top_corr
        else:
            righe.append(_crea_riga(corrente, pagina_idx, start_idx + len(righe)))
            corrente = [w]
            top_corr = w["top"]
    if corrente:
        righe.append(_crea_riga(corrente, pagina_idx, start_idx + len(righe)))
    return righe


def unisci_token(parole: list[dict]) -> list[dict]:
    """Riunisce token spezzati: ['557,', '34'] -> '557,34'; ['1', '576,00'] -> '1576,00';
    ['1.234,56', 'D'] -> segno_lettera; toglie il simbolo €."""
    toks = []
    for w in parole:
        w = dict(w)
        w["text"] = w["text"].replace("\x19", "").strip()
        if w["text"] and w["text"] != "€":
            t = w["text"].replace("€", "").strip()
            if t and is_importo(t):
                w["text"] = t
            toks.append(w)
    cambiato = True
    while cambiato and len(toks) > 1:
        cambiato = False
        for i in range(len(toks) - 1):
            a, b = toks[i], toks[i + 1]
            if (b["x0"] - a["x1"]) >= 8:
                continue
            if is_importo(a["text"]) and b["text"] in ("D", "A"):
                a["segno_lettera"] = b["text"]; a["x1"] = b["x1"]
                del toks[i + 1]; cambiato = True; break
            comb = a["text"] + b["text"]
            # '557,'+'34'  |  '1'+'576,00'  |  '1.'+'234,56'
            if is_importo(comb) and not (is_importo(a["text"]) and is_importo(b["text"])):
                a["text"] = comb; a["x1"] = b["x1"]
                del toks[i + 1]; cambiato = True; break
    return toks


def estrai_righe(percorso: str) -> Documento:
    righe: list[Riga] = []
    testi = []
    n = 0
    for pi, (parole, testo_pagina) in enumerate(pagine_parole(percorso)):
        righe.extend(_righe_pagina(parole, pi, len(righe)))
        testi.append(testo_pagina)
        n = pi + 1
    testo = "\n".join(testi)
    return Documento(righe=righe, testo=testo, pagine=n, banca=rileva_banca(testo))


def rileva_banca(testo: str) -> str:
    t = testo.lower()
    for nome, pat in BANCHE:
        if re.search(pat, t):
            return nome
    return "Sconosciuta"


# ---------------------------------------------------------------------------
# Intestazioni
# ---------------------------------------------------------------------------
def _classe_intestazione(tok: str) -> Optional[str]:
    t = tok.lower().strip(":.")
    if any(t.startswith(p) for p in PREF_SALDO): return "saldo"
    if any(t.startswith(p) for p in PREF_DARE): return "dare"
    if any(t.startswith(p) for p in PREF_AVERE): return "avere"
    if any(t.startswith(p) for p in PREF_IMPORTO): return "importo"
    return None


def rileva_colonne(riga: Riga) -> Optional[Colonne]:
    toks = [w["text"].lower().strip(":.") for w in riga.parole]
    if any(is_importo(t) or is_data(t) for t in toks):
        return None
    col = Colonne()
    trovate = 0
    i = 0
    parole = riga.parole
    while i < len(parole):
        w = parole[i]
        cls = _classe_intestazione(w["text"])
        x0, x1 = w["x0"], w["x1"]
        # "IN ENTRATA" / "IN USCITA": la parola utile è la successiva
        if cls is None and w["text"].lower() == "in" and i + 1 < len(parole):
            cls = _classe_intestazione(parole[i + 1]["text"])
            x1 = parole[i + 1]["x1"]
            i += 1
        # "Addebi" + "ti" spezzato
        elif cls and i + 1 < len(parole) and (parole[i + 1]["x0"] - x1) < 8 and len(parole[i + 1]["text"]) <= 3 and not _classe_intestazione(parole[i + 1]["text"]):
            x1 = parole[i + 1]["x1"]
            i += 1
        if cls:
            centro = (x0 + x1) / 2
            # l'importo è allineato a destra: spostiamo il centro verso destra
            centro_dx = x1 - 12
            if getattr(col, cls) is None:
                setattr(col, cls, centro_dx if cls != "saldo" else centro)
                trovate += 1
        i += 1
    ha_tabella = bool(set(toks) & PAROLE_TABELLA)
    if (col.dare is not None and col.avere is not None) or (trovate >= 2 and ha_tabella) or (col.importo is not None and ha_tabella):
        return col
    return None


# ---------------------------------------------------------------------------
# Segno
# ---------------------------------------------------------------------------
PAROLE_USCITA = ("addebito", "pagamento", "prelievo", "prelevamento", "commission", "canone", "imposta",
                 "bollo", "a favore di", "da voi disposto", "disposto", "disposizione", "rid", "sdd", "pos", "carta",
                 "spese", "competenze", "f24", "ricarica", "mav", "rav", "bollettino", "outgoing", "buy", "acquisto")
PAROLE_ENTRATA = ("accredito", "stipendio", "versamento", "a vostro favore", "ricevuto", "rimborso",
                  "interessi attivi", "giroconto in entrata", "pensione", "incasso", "incoming", "sell", "vendita", "dividend")


def segno_da_descrizione(desc: str) -> int:
    d = desc.lower()
    for p in PAROLE_ENTRATA:
        if p in d:
            return 1
    for p in PAROLE_USCITA:
        if p in d:
            return -1
    return -1


# ---------------------------------------------------------------------------
# Parser generico
# ---------------------------------------------------------------------------
@dataclass
class _Sospeso:
    mov: Movimento
    completo: bool


def _date_in_testa(parole: list[dict], anno: Optional[int]) -> tuple[list[date], int]:
    out: list[date] = []
    i = 0
    while i < len(parole) and i < 2:
        d = parse_data(parole[i]["text"], anno)
        if d is None:
            break
        out.append(d)
        i += 1
    return out, i


def _importi_colonne(parole: list[dict], col: Optional[Colonne]):
    """Restituisce (dare, avere, importo_singolo, lista_ids_importi_usati, importi_fuori_colonna)."""
    dare = avere = singolo = None
    usati: set[int] = set()
    fuori = []
    segno_singolo = None
    for w in parole:
        v = parse_importo(w["text"])
        if v is None:
            continue
        cx = (w["x0"] + w["x1"]) / 2
        where = col.colonna_di(cx) if col else None
        if where == "dare" and dare is None:
            dare = v; usati.add(id(w))
        elif where == "avere" and avere is None:
            avere = v; usati.add(id(w))
        elif where == "importo" and singolo is None:
            singolo = v; usati.add(id(w)); segno_singolo = w.get("segno_lettera") or ("-" if "-" in w["text"] else "+" if "+" in w["text"] else None)
        elif where == "saldo":
            usati.add(id(w))
        else:
            fuori.append((w, v))
    return dare, avere, singolo, segno_singolo, usati, fuori


def _valore(dare, avere, singolo, segno_singolo, fuori, descrizione, col) -> Optional[Decimal]:
    if dare is not None and avere is None:
        return -abs(dare)
    if avere is not None and dare is None:
        return abs(avere)
    if dare is not None and avere is not None:
        return abs(avere) - abs(dare)
    if singolo is not None:
        if segno_singolo == "D": return -abs(singolo)
        if segno_singolo == "A": return abs(singolo)
        if segno_singolo in ("-", "+"): return singolo
        return abs(singolo) * segno_da_descrizione(descrizione)
    if col is not None and col.note:
        return None  # con colonne note, un importo fuori colonna non è il movimento
    if not fuori:
        return None
    if len(fuori) >= 3:
        fuori = fuori[:-1]
    if len(fuori) == 2:
        v1, v2 = fuori[0][1], fuori[1][1]
        return abs(v2) - abs(v1)
    w, v = fuori[0]
    if w.get("segno_lettera") == "D": return -abs(v)
    if w.get("segno_lettera") == "A": return abs(v)
    if "-" in w["text"] or "+" in w["text"]: return v
    return abs(v) * segno_da_descrizione(descrizione)


def parse_generico(doc: Documento) -> Risultato:
    ris = Risultato(banca=doc.banca, metodo="generico", pagine=doc.pagine)
    righe = doc.righe
    if not righe or len(doc.testo.strip()) < 50:
        ris.avvisi.append("Il PDF non contiene testo leggibile (probabile scansione): serve l'OCR.")
        return ris

    anno = anno_prevalente(righe)
    col: Optional[Colonne] = None
    movimenti: list[Movimento] = []
    sospeso: Optional[_Sospeso] = None

    for r in righe:
        nuova_col = rileva_colonne(r)
        if nuova_col is not None:
            col = nuova_col
            continue
        testo_r = r.testo.strip()
        if RE_RIGA_SERVIZIO.match(testo_r):
            continue
        if RE_SALDO_INIZIALE.search(testo_r):
            sospeso = None
            continue
        if RE_SALDO_FINALE.search(testo_r):
            sospeso = None
            if movimenti and importi_in_testo(testo_r):
                break          # dopo il saldo finale ci sono solo note e tabelle accessorie
            continue

        parole = unisci_token(r.parole)
        if not parole:
            continue
        date_trovate, i = _date_in_testa(parole, anno)

        if date_trovate:
            # nuovo movimento (eventualmente senza importo: resta in sospeso)
            dare, avere, singolo, segno_s, usati, fuori = _importi_colonne(parole[i:], col)
            desc_tok = [w["text"] for w in parole[i:] if id(w) not in usati and not (col and col.note and parse_importo(w["text"]) is not None and _importo_in_colonna(w, col))]
            if col is None or not col.note:
                ids_fuori = {id(w) for w, _ in fuori}
                desc_tok = [w["text"] for w in parole[i:] if id(w) not in ids_fuori]
            if desc_tok and len(date_trovate) == 1 and is_data(desc_tok[-1]):
                dv = parse_data(desc_tok.pop(), anno)
                if dv: date_trovate.append(dv)
            descrizione = " ".join(desc_tok).strip(" -:|")
            valore = _valore(dare, avere, singolo, segno_s, fuori, descrizione, col)
            mov = Movimento(
                data=date_trovate[0],
                data_valuta=date_trovate[1] if len(date_trovate) > 1 else None,
                descrizione=descrizione,
                importo=valore if valore is not None else Decimal("0"),
                riga_origine=r.idx,
            )
            if valore is not None:
                movimenti.append(mov)
                sospeso = _Sospeso(mov, True)
            else:
                sospeso = _Sospeso(mov, False)
            continue

        # riga senza data: continuazione o completamento del sospeso
        if sospeso is None:
            continue
        if len(testo_r) > 140 or is_data(parole[0]["text"]):
            sospeso = None
            continue
        dare, avere, singolo, segno_s, usati, fuori = _importi_colonne(parole, col)
        if not sospeso.completo and (dare is not None or avere is not None or singolo is not None):
            desc_extra = " ".join(w["text"] for w in parole if id(w) not in usati)
            m = sospeso.mov
            m.descrizione = (m.descrizione + " " + desc_extra).strip()
            v = _valore(dare, avere, singolo, segno_s, [], m.descrizione, col)
            if v is not None:
                m.importo = v
                movimenti.append(m)
                sospeso.completo = True
            continue
        if sospeso.completo and (dare is not None or avere is not None or singolo is not None):
            # un altro importo nelle colonne senza data: non è una continuazione
            sospeso = None
            continue
        # continuazione pura (anche con sotto-importi fuori colonna)
        sospeso.mov.descrizione = (sospeso.mov.descrizione + " " + testo_r).strip()

    # scarta i movimenti fuori dal periodo dell'estratto (tabelle accessorie, anni precedenti)
    periodo = periodo_estratto(righe)
    if periodo:
        d0, d1 = periodo
        fuori = [m for m in movimenti if not (d0 <= m.data <= d1 + timedelta(days=10))]
        if fuori and len(fuori) < len(movimenti) / 2:
            movimenti = [m for m in movimenti if m not in fuori]
    for m in movimenti:
        m.descrizione = re.sub(r"\s{2,}", " ", m.descrizione).strip()
    ris.movimenti = movimenti
    ris.metodo = "generico" + ("+colonne" if col else "")
    iniz, fin, avv = cerca_saldi(righe)
    ris.avvisi.extend(avv)
    ris.quadratura = calcola_quadratura(iniz, fin, movimenti)
    if not movimenti:
        ris.avvisi.append("Nessun movimento riconosciuto. Il layout di questa banca non è ancora supportato.")
    return ris


def _importo_in_colonna(w: dict, col: Colonne) -> bool:
    return col.colonna_di((w["x0"] + w["x1"]) / 2) is not None


def _data_in(testo: str) -> Optional[date]:
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", testo)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def periodo_estratto(righe: list[Riga]) -> Optional[tuple[date, date]]:
    """(data saldo iniziale, data saldo finale) se entrambe presenti."""
    d0 = d1 = None
    for r in righe:
        t = r.testo
        if "saldo" not in t.lower():
            continue
        if d0 is None and RE_SALDO_INIZIALE.search(t):
            d0 = _data_in(t)
        elif RE_SALDO_FINALE.search(t):
            d = _data_in(t)
            if d and (d0 is None or d >= d0) and (d1 is None or d >= d1):
                d1 = d
    return (d0, d1) if d0 and d1 else None


def cerca_saldi(righe: list[Riga]) -> tuple[Optional[Decimal], Optional[Decimal], list[str]]:
    iniziale = finale = finale_debole = None
    data_iniziale = data_finale = None
    avvisi = []
    for r in righe:
        t = r.testo.replace("\x19", "")
        if "saldo" not in t.lower():
            continue
        importi = importi_in_testo(t)
        if not importi:
            continue
        d = _data_in(t)
        if iniziale is None and RE_SALDO_INIZIALE.search(t):
            iniziale, data_iniziale = importi[-1], d
        elif RE_SALDO_FINALE.search(t):
            # un saldo finale datato prima del saldo iniziale appartiene a un altro periodo
            if d and data_iniziale and d < data_iniziale:
                continue
            if d and data_finale and d < data_finale:
                continue
            finale, data_finale = importi[-1], d
        elif RE_SALDO_FINALE_DEBOLE.search(t):
            finale_debole = importi[-1]
    if finale is None:
        finale = finale_debole
    if iniziale is None:
        avvisi.append("Saldo iniziale non trovato nel PDF: quadratura non verificabile.")
    if finale is None:
        avvisi.append("Saldo finale non trovato nel PDF: quadratura non verificabile.")
    return iniziale, finale, avvisi


def anno_prevalente(righe: list[Riga]) -> Optional[int]:
    anni: dict[int, int] = {}
    for r in righe:
        for w in r.parole[:2]:
            d = parse_data(w["text"])
            if d:
                anni[d.year] = anni.get(d.year, 0) + 1
    return max(anni, key=anni.get) if anni else None


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------
def analizza_pdf(percorso: str) -> Risultato:
    doc = estrai_righe(percorso)
    from .banche import template_per
    tpl = template_per(doc)
    if tpl is not None:
        ris = tpl(doc)
        if ris.movimenti:
            return ris
    return parse_generico(doc)

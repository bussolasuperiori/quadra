"""Crea una copia anonimizzata di un estratto conto reale, mantenendo il layout.

Ogni parola del PDF viene ridisegnata nella stessa posizione (reportlab) dopo essere
passata da questi filtri:
- IBAN, codici fiscali, email, telefoni, numeri lunghi  -> valori finti con lo stesso formato
- parole "sensibili" indicate a mano (nomi, vie, città)  -> pseudonimi fissi
- parole in MAIUSCOLO o Capitalizzate non in whitelist   -> pseudonimi deterministici
- importi dei movimenti                                  -> importi casuali dello stesso ordine
  di grandezza; saldi, totali e saldo progressivo vengono RICALCOLATI così la quadratura resta vera.

Uso:
  python -m tests.anonimizza input.pdf output.pdf --sensibili "Mario Rossi,Via Verdi,Milano"
Il file di input NON viene mai copiato nel repository.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import re
import sys
from decimal import Decimal

import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

sys.path.insert(0, ".")
from engine import converti  # noqa: E402
from engine.numeri import parse_importo, formatta_importo, is_importo, is_data  # noqa: E402
from engine.parser import estrai_righe, unisci_token, RE_SALDO_INIZIALE, RE_SALDO_FINALE  # noqa: E402

# parole comuni negli estratti conto che NON vanno pseudonimizzate anche se maiuscole/capitalizzate
WHITELIST = set("""
ESTRATTO CONTO AL N C/C IBAN BIC DATA VALUTA DESCRIZIONE ADDEBITI ACCREDITI SALDO TIPO IN ENTRATA USCITA
PRODOTTO INIZIALE FINALE TRANSAZIONI SUL RIASSUNTIVO PANORAMICA DEL CONTI FIDUCIARI FONDI MERCATO MONETARIO
ISIN UNITÀ PREZZO PER UNITÀ VALORE DI EURO IMPORTO UNITARIO NOTE SULL'ESTRATTO QUOTA CAPITALE INTERESSI
ARRETRATI/ALTRO MUTUO COD. DISP.: NOME: MANDATO: MITT.: BENEF.: ORD.: CASH NOTPROVIDED POS ADUE BANCOMAT PAY
EFFETTUATO IL ALLE ORE MEDIANTE LA CARTA PRESSO MILANO TORINO ROMA XXXX ABI SEPA SDD RID F24 ATM USD EUR ETF
UCITS PLC ICAV ACC DL ID.OP. Q.TA' A SPA S.P.A. S.R.L. SRL LTD GMBH BANK BRANCH ITALY VIA PIAZZA CORSO
Saldo Totale Dettaglio Data Operazione Valuta Descrizione Addebiti Accrediti Pagina Pagamento Tramite Bonifico
Vostro favore disposto Voi Carta Interessi Imposte Commercio Rendimento Interest Incoming Outgoing Buy Sell Savings
Dividend Cash Stamp Duty Tax Portfolio Global India Managed Euro Fund Deutsche Acquisto Vendita Conto corrente
Informazioni utili Coordinate bancarie Tipologia conto Filiale di appoggio del rapporto Riepilogo Per qualsiasi
informazione parli con Il suo gestore presso la filiale Anche da app e sito La Digitale Numero verde dall'Italia
dall'estero pagamento App Mobile su store Android iOS Dal lunedì al venerdì dalle Il sabato e la domenica Negli
altri orari risponde l'assistente digitale Ci segua anche su Telefono filiale Cell Generato il Europe Rome Sede
centrale Direttore Generale Registro commerciale HRB tribunale locale di Charlottenburg Germania Camera Commercio
Trade Republic Bank Italy Spaces Gae Aulenti Torre Brunnenstrasse Berlino Intesa Sanpaolo Ellis Rimborso spese
Nota giugno luglio agosto settembre ottobre Rata macchina foto video Giugno Luglio Agosto Settembre Ottobre
Investimenti PayPal Europe Cie Fastweb Amazon Tigros Netflix Spotify Esselunga Carrefour Lidl Coop Conad Enel
set ott nov dic gen feb mar apr mag giu lug ago quantity Accumulating Acc execution plan trade transfer from for
payment Si prega di controllare l'estratto conto in quanto le contestazioni devono essere fatte valere
""".split())

MESI_RX = re.compile(r"^(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)$", re.I)
RE_IBAN = re.compile(r"\(?IT\d{2}[A-Z]\d{5}\d{5}[A-Z0-9]{12}\)?")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_LUNGO = re.compile(r"\d{5,}")
RE_CF = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")
RE_CARTA = re.compile(r"^(?:n\.)?5\d{3}$|^X{2}\d{2}$")

NOMI = ["Bianchi", "Ferrari", "Colombo", "Ricci", "Greco", "Fontana", "Conti", "Marino", "Costa", "Galli",
        "Rinaldi", "Mancini", "Villa", "Serra", "Longo", "Moretti", "Lombardi", "Barbieri", "Ferraro", "Santoro"]
PAROLE = ["Alpha", "Bravo", "Delta", "Echo", "Lima", "Nova", "Orion", "Polar", "Quark", "Sigma", "Tango", "Vega",
          "Zenit", "Argo", "Brio", "Cielo", "Duna", "Faro", "Giro", "Lago", "Mare", "Nido", "Onda", "Pino", "Rete"]


def _hash(s: str) -> int:
    return int(hashlib.md5(s.lower().encode()).hexdigest(), 16)


def pseudonimo(parola: str) -> str:
    h = _hash(parola)
    base = NOMI[h % len(NOMI)] if parola[:1].isupper() and parola[1:2].islower() else PAROLE[h % len(PAROLE)].upper()
    # mantieni la lunghezza approssimativa e la punteggiatura finale
    coda = ""
    while parola and parola[-1] in ".,:;)'":
        coda = parola[-1] + coda
        parola = parola[:-1]
    if parola.isupper():
        base = base.upper()
    return base + coda


def cifre_finte(m: re.Match) -> str:
    s = m.group()
    rnd = random.Random(_hash(s))
    return "".join(str(rnd.randint(0, 9)) for _ in s)


def filtra_parola(t: str, sensibili: list[str]) -> str:
    low = t.lower()
    if "*" in t:                       # carte mascherate tipo 5167*********381
        return re.sub(r"\d", "0", t)
    for s in sensibili:
        if s.lower() in low:
            return pseudonimo(t)
    if RE_IBAN.search(t):
        return RE_IBAN.sub(lambda m: ("(" if m.group().startswith("(") else "") + "IT00X0000000000000000000000" + (")" if m.group().endswith(")") else ""), t)
    if RE_EMAIL.search(t):
        return "nome.cognome@esempio.it"
    if RE_CF.match(t):
        return "RSSMRA80A01F205X"
    if is_importo(t) or is_data(t) or MESI_RX.match(t) or re.fullmatch(r"[\d.,:/%+\-]+", t):
        return RE_LUNGO.sub(cifre_finte, t)
    if RE_LUNGO.search(t):
        return RE_LUNGO.sub(cifre_finte, t)
    nucleo = t.strip(".,:;()'\"")
    if nucleo.lower().startswith(("addeb", "accred", "dare", "avere", "entrat", "uscit", "saldo", "import", "descr", "data", "valut")):
        return t
    if nucleo in WHITELIST or nucleo.lower() in {w.lower() for w in WHITELIST}:
        return t
    if len(nucleo) >= 3 and (nucleo.isupper() or (nucleo[0].isupper() and nucleo[1:].islower())) and nucleo.isalpha():
        return pseudonimo(t)
    return t


def anonimizza(src: str, dst: str, sensibili: list[str]) -> None:
    ris = converti(src)
    doc = estrai_righe(src)
    rnd = random.Random(42)

    # 1) nuovi importi per ogni movimento (stesso ordine di grandezza, stesso segno)
    nuovi: dict[int, Decimal] = {}
    for m in ris.movimenti:
        a = abs(m.importo)
        if a == 0:
            nuovo = Decimal("0.00")
        else:
            lo, hi = a * Decimal("0.5"), a * Decimal("1.6")
            nuovo = (lo + (hi - lo) * Decimal(str(rnd.random()))).quantize(Decimal("0.01"))
        nuovi[id(m)] = nuovo if m.importo > 0 else -nuovo
    per_riga = {m.riga_origine: m for m in ris.movimenti}
    q = ris.quadratura
    tot_e = sum((v for v in nuovi.values() if v > 0), Decimal(0))
    tot_u = sum((v for v in nuovi.values() if v < 0), Decimal(0))
    saldo_in = (abs(q.saldo_iniziale) if q and q.saldo_iniziale is not None else Decimal("1000")) * Decimal("0.8")
    if saldo_in + tot_e + tot_u < 0:
        saldo_in = -(tot_e + tot_u) + Decimal("250.00")
    saldo_in = saldo_in.quantize(Decimal("0.01"))
    saldo_fin = saldo_in + tot_e + tot_u
    vecchio_in = q.saldo_iniziale if q else None
    vecchio_fin = q.saldo_finale if q else None
    vecchia_e, vecchia_u = ris.entrate, ris.uscite

    # mappa importo-vecchio -> importo-nuovo per riepiloghi/totali
    sostituzioni_globali = {}
    for vecchio, nuovo in ((vecchio_in, saldo_in), (vecchio_fin, saldo_fin), (vecchia_e, tot_e), (-vecchia_u, -tot_u)):
        if vecchio is not None:
            sostituzioni_globali[abs(vecchio).quantize(Decimal("0.01"))] = abs(nuovo)
    # "saldo del periodo"
    if vecchio_in is not None and vecchio_fin is not None:
        sostituzioni_globali[abs(vecchio_fin - vecchio_in).quantize(Decimal("0.01"))] = abs(saldo_fin - saldo_in)

    # saldo progressivo (Trade Republic): ricalcolato movimento per movimento
    progressivo = {}
    s = saldo_in
    for m in ris.movimenti:
        s += nuovi[id(m)]
        vecchio_prog = getattr(m, "saldo_progressivo", None)
        if vecchio_prog is not None:
            progressivo[abs(vecchio_prog).quantize(Decimal("0.01"))] = s

    with pdfplumber.open(src) as pdf:
        c = canvas.Canvas(dst, pagesize=(pdf.pages[0].width, pdf.pages[0].height))
        for pi, page in enumerate(pdf.pages):
            c.setPageSize((page.width, page.height))
            righe = [r for r in doc.righe if r.pagina == pi]
            mov_corrente = None
            righe_dal_mov = 0
            importo_mov_fatto = False
            for r in righe:
                if r.idx in per_riga:
                    mov_corrente, righe_dal_mov, importo_mov_fatto = per_riga[r.idx], 0, False
                else:
                    righe_dal_mov += 1
                    if righe_dal_mov > 3:
                        mov_corrente = None
                mov = mov_corrente
                in_saldo = bool(RE_SALDO_INIZIALE.search(r.testo) or RE_SALDO_FINALE.search(r.testo))
                toks = unisci_token(r.parole)
                for w in toks:
                    t = w["text"]
                    nuovo_t = None
                    v = parse_importo(t)
                    if v is not None:
                        av = abs(v).quantize(Decimal("0.01"))
                        if mov is not None and not importo_mov_fatto and av == abs(mov.importo).quantize(Decimal("0.01")):
                            nuovo_t = _riformatta(t, abs(nuovi[id(mov)]))
                            importo_mov_fatto = True
                        elif av in progressivo:
                            nuovo_t = _riformatta(t, progressivo[av])
                        elif av in sostituzioni_globali:
                            nuovo_t = _riformatta(t, sostituzioni_globali[av])
                        elif in_saldo:
                            nuovo_t = _riformatta(t, abs(v) * Decimal("0.8"))
                        else:
                            nuovo_t = _riformatta(t, (abs(v) * Decimal(str(0.6 + rnd.random()))).quantize(Decimal("0.01")))
                    else:
                        nuovo_t = filtra_parola(t, sensibili)
                        riga_low = r.testo.lower()
                        if "iban" in riga_low and re.fullmatch(r"[A-Z]{2}\d{2}|\d{3,4}|[A-Z]\d{3}", t):
                            nuovo_t = "IT00" if t[:2].isalpha() and len(t) == 4 else "0" * len(t)
                        if "carta" in riga_low and re.fullmatch(r"(n\.)?\d{4}", t):
                            nuovo_t = t[:-4] + "0000"
                        if re.match(r"X{2}\d{2}", t):
                            nuovo_t = "XX00" + t[4:]
                        if re.fullmatch(r"(n\.)?\d{4}", t) and "5167" in t:
                            nuovo_t = t[:-4] + "0000"
                    size = max(5.0, min(14.0, (w["bottom"] - w["top"]) * 0.95))
                    font = "Helvetica-Bold" if "Bold" in str(w.get("fontname", "")) else "Helvetica"
                    c.setFont(font, size)
                    y = page.height - w["bottom"] + size * 0.2
                    # importi allineati a destra, come nell'originale
                    if v is not None:
                        c.drawRightString(w["x1"], y, nuovo_t)
                    else:
                        larg = stringWidth(nuovo_t, font, size)
                        disponibile = w["x1"] - w["x0"]
                        if larg > disponibile * 1.3 and disponibile > 0:
                            c.setFont(font, max(4.5, size * disponibile / larg))
                        c.drawString(w["x0"], y, nuovo_t)
            c.showPage()
        c.save()
    print(f"scritto {dst}: {len(ris.movimenti)} movimenti, saldo iniziale {formatta_importo(saldo_in)}, finale {formatta_importo(saldo_fin)}")


def _riformatta(originale: str, valore: Decimal) -> str:
    """Rende il nuovo valore con lo stesso stile dell'originale (separatori, segno, €)."""
    s = formatta_importo(valore)              # 1.234,56
    if "." not in originale.replace(",", "").rstrip("0123456789") and not re.search(r"\d\.\d{3},", originale):
        s = s.replace(".", "")                 # stile senza separatore migliaia (es. Intesa)
    pre = "+" if originale.startswith("+") else "-" if originale.startswith("-") else ""
    post = "-" if originale.endswith("-") else ""
    return pre + s + post


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--sensibili", default="", help="parole da sostituire sempre, separate da virgola")
    a = ap.parse_args()
    anonimizza(a.src, a.dst, [s.strip() for s in a.sensibili.split(",") if s.strip()])

"""API Quadra — conversione estratti conto PDF.

Avvio locale:  uvicorn api.main:app --reload --port 8000
Privacy: ogni PDF viene scritto in un file temporaneo, analizzato e cancellato
subito; il risultato resta in memoria solo per il tempo di un download (TTL).
"""
from __future__ import annotations

import io
import json
import os
import secrets
import tempfile
import time
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from engine import converti, to_csv, to_xlsx, Risultato
from engine.export import to_xlsx_multiplo
from api import quote
from web.banche import BANCHE, PER_SLUG, pagina_banca, pagina_indice, sitemap

MAX_MB = int(os.environ.get("QUADRA_MAX_MB", "15"))
MAX_FILE = int(os.environ.get("QUADRA_MAX_FILES", "12"))
TTL_SEC = int(os.environ.get("QUADRA_TTL_SEC", "900"))        # 15 minuti
SEGNALAZIONI_DIR = Path(os.environ.get("QUADRA_SEGNALAZIONI", "/tmp/quadra_segnalazioni"))
BASE_URL = os.environ.get("QUADRA_BASE_URL", "https://quadra-mfai.onrender.com").rstrip("/")
GTAG_ID = os.environ.get("QUADRA_GTAG_ID", "").strip()           # es. AW-123456789 o G-XXXXXXX
ADS_CONV = os.environ.get("QUADRA_ADS_CONVERSION", "").strip()    # es. AW-123456789/AbCdEfGh (etichetta conversione)

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Quadra API", version="0.5.0")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

# token -> (timestamp, [(nome_file, Risultato), ...])
_cache: dict[str, tuple[float, list[tuple[str, Risultato]]]] = {}
_lock = threading.Lock()


def _pulisci():
    adesso = time.time()
    with _lock:
        for k in [k for k, (t, _) in _cache.items() if adesso - t > TTL_SEC]:
            _cache.pop(k, None)


def _tag_html() -> str:
    """Snippet Google tag (Ads/GA4) solo se configurato: così il codice resta pulito senza tracciamento."""
    if not GTAG_ID:
        return "<script>window.quadraTrack=function(){};</script>"
    conv = f"gtag('event','conversion',{{'send_to':'{ADS_CONV}'}});" if ADS_CONV else ""
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={GTAG_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GTAG_ID}',{{'anonymize_ip':true}});
window.quadraTrack=function(nome,dati){{try{{gtag('event',nome,dati||{{}});if(nome==='conversione_ok'){{{conv}}}}}catch(e){{}}}};</script>"""


def _pagina(nome: str) -> str:
    html = (WEB / nome).read_text(encoding="utf-8")
    return html.replace("</head>", _tag_html() + "\n</head>", 1)


@app.get("/", response_class=HTMLResponse)
def home():
    return _pagina("index.html")


@app.get("/commercialisti", response_class=HTMLResponse)
def commercialisti():
    return _pagina("commercialisti.html")


@app.get("/banche", response_class=HTMLResponse)
def banche_indice():
    return pagina_indice().replace("</head>", _tag_html() + "</head>", 1)


@app.get("/banche/{slug}", response_class=HTMLResponse)
def banca_pagina(slug: str):
    b = PER_SLUG.get(slug)
    if not b:
        raise HTTPException(404, "Banca non trovata")
    return pagina_banca(b).replace("</head>", _tag_html() + "</head>", 1)


@app.get("/sitemap.xml")
def sitemap_xml():
    return Response(sitemap(BASE_URL), media_type="application/xml")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {BASE_URL}/sitemap.xml\n"


@app.get("/health")
def health():
    return {"ok": True, "versione": app.version}


def _converti_upload(dati: bytes, nome: str) -> Risultato:
    if not dati.startswith(b"%PDF"):
        raise HTTPException(400, f"{nome}: non sembra un PDF valido.")
    if len(dati) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"{nome}: supera {MAX_MB} MB.")
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dati)
        try:
            return converti(tmp)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"{nome}: non sono riuscito a leggere il PDF ({type(e).__name__}).") from e
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _visitatore(request: Request) -> tuple[str, Optional[str]]:
    """(id visitatore, nuovo qid da impostare come cookie se mancava)."""
    qid = request.cookies.get("qid")
    nuovo = None
    if not qid or len(qid) < 16:
        qid = nuovo = secrets.token_urlsafe(24)
    return quote.id_visitatore(qid, None), nuovo


def _imposta_qid(risp: Response, nuovo: Optional[str]) -> Response:
    if nuovo:
        risp.set_cookie("qid", nuovo, max_age=400 * 24 * 3600, samesite="lax", httponly=True)
    return risp


@app.post("/api/converti")
async def converti_pdf(request: Request, file: list[UploadFile] = File(...), gruppo: str = Form("")):
    """Accetta uno o più PDF. Risposta: un token unico + un risultato per file.
    Se `gruppo` è il token di una conversione precedente (non scaduta), i nuovi file
    vengono aggiunti a quel gruppo: il browser può così inviare un file alla volta."""
    _pulisci()
    if not file:
        raise HTTPException(400, "Carica almeno un file PDF.")
    if len(file) > MAX_FILE:
        raise HTTPException(400, f"Massimo {MAX_FILE} file per volta.")
    vis, nuovo_qid = _visitatore(request)
    rimaste = quote.pagine_rimaste(vis)
    risultati: list[tuple[str, Risultato]] = []
    for f in file:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"{f.filename or 'file'}: carica solo PDF.")
        dati = await f.read()
        ris = _converti_upload(dati, f.filename)
        if rimaste is not None and ris.pagine > rimaste:
            quote.registra_evento("limite", visitatore=vis, pagine_richieste=ris.pagine, rimaste=rimaste)
            msg = (f"Hai usato le {quote.FREE_PAGES} pagine gratuite di questo mese "
                   f"(questo PDF ne ha {ris.pagine}, te ne restano {rimaste}). "
                   "Lascia la tua email qui sotto: ti avvisiamo appena il piano Base è attivo.")
            return _imposta_qid(JSONResponse({"detail": msg, "limite": True}, status_code=402), nuovo_qid)
        if rimaste is not None:
            rimaste -= ris.pagine
        quote.consuma(vis, ris.pagine)
        risultati.append((Path(f.filename).stem, ris))
    quote.registra_evento("conversione", visitatore=vis, n_file=len(file),
                          pagine=sum(r.pagine for _, r in risultati),
                          banche=[r.banca for _, r in risultati],
                          quadra=[bool(r.quadratura and r.quadratura.quadra) for _, r in risultati])

    with _lock:
        voce = _cache.get(gruppo) if gruppo else None
        if voce is not None and len(voce[1]) + len(risultati) <= MAX_FILE:
            token = gruppo
            risultati = voce[1] + risultati
        else:
            token = secrets.token_urlsafe(16)
        _cache[token] = (time.time(), risultati)

    corpo = {
        "token": token,
        "n_file": len(risultati),
        "file": [dict(ris.to_dict(), nome_file=nome) for nome, ris in risultati],
    }
    # retro-compatibilità: i campi del primo file anche al primo livello
    primo = corpo["file"][0]
    for k in ("banca", "metodo", "pagine", "n_movimenti", "entrate", "uscite", "movimenti", "quadratura", "avvisi", "nome_file"):
        corpo[k] = primo[k]
    corpo["pagine_rimaste"] = quote.pagine_rimaste(vis)
    corpo["pagine_gratis"] = quote.FREE_PAGES
    return _imposta_qid(JSONResponse(corpo), nuovo_qid)


def _prendi(token: str) -> list[tuple[str, Risultato]]:
    _pulisci()
    with _lock:
        voce = _cache.get(token)
    if not voce:
        raise HTTPException(404, "Risultato scaduto: ricarica il PDF.")
    return voce[1]


def _nome_download(ris_list: list[tuple[str, Risultato]]) -> str:
    return ris_list[0][0] if len(ris_list) == 1 else f"quadra_{len(ris_list)}_estratti"


@app.get("/api/scarica/{token}.xlsx")
def scarica_xlsx(token: str):
    ris_list = _prendi(token)
    dati = to_xlsx(ris_list[0][1]) if len(ris_list) == 1 else to_xlsx_multiplo(ris_list)
    return Response(
        dati,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_nome_download(ris_list)}_quadra.xlsx"'},
    )


@app.get("/api/scarica/{token}.csv")
def scarica_csv(token: str):
    ris_list = _prendi(token)
    if len(ris_list) == 1:
        return Response(
            ("﻿" + to_csv(ris_list[0][1])).encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{ris_list[0][0]}_quadra.csv"'},
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, ris in ris_list:
            z.writestr(f"{nome}_quadra.csv", "﻿" + to_csv(ris))
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_nome_download(ris_list)}_csv.zip"'},
    )


@app.post("/api/segnala")
async def segnala(
    file: UploadFile = File(...),
    email: str = Form(""),
    banca: str = Form(""),
    note: str = Form(""),
    consenso: str = Form(""),
):
    """L'utente ci manda volontariamente un PDF che non viene letto bene.
    Viene conservato (solo con consenso esplicito) per aggiungere il template della banca."""
    if consenso.lower() not in ("on", "true", "1", "si", "sì", "yes"):
        raise HTTPException(400, "Serve il consenso esplicito a conservare il file per l'analisi.")
    dati = await file.read()
    if not dati.startswith(b"%PDF") or len(dati) > MAX_MB * 1024 * 1024:
        raise HTTPException(400, "File non valido o troppo grande.")
    SEGNALAZIONI_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = SEGNALAZIONI_DIR / f"{stamp}_{secrets.token_hex(4)}"
    base.with_suffix(".pdf").write_bytes(dati)
    base.with_suffix(".json").write_text(json.dumps({
        "email": email.strip()[:200], "banca": banca.strip()[:100], "note": note.strip()[:1000],
        "nome_file": file.filename, "ricevuto": stamp,
    }, ensure_ascii=False, indent=2))
    quote.registra_evento("segnalazione", email=email.strip()[:200], banca=banca.strip()[:100], file=str(base.name))
    return {"ok": True, "messaggio": "Grazie! Analizziamo il layout e ti scriviamo quando è supportato."}


@app.get("/campione.pdf")
def campione():
    p = Path(__file__).resolve().parent.parent / "tests" / "samples" / "reale_intesa_xme.pdf"
    if not p.exists():
        p = p.with_name("dare_avere.pdf")
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), media_type="application/pdf", filename="estratto_conto_esempio.pdf")


@app.get("/esempio.xlsx")
def esempio_xlsx():
    """Excel prodotto dall'estratto di esempio: usato come allegato/link nelle mail di contatto."""
    p = Path(__file__).resolve().parent.parent / "tests" / "samples" / "reale_intesa_xme.pdf"
    if not p.exists():
        raise HTTPException(404)
    return Response(
        to_xlsx(converti(str(p))),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Esempio_Quadra_estratto_Intesa.xlsx"'},
    )


@app.post("/api/lista-attesa")
async def lista_attesa(request: Request, email: str = Form(...), piano: str = Form("base"), note: str = Form("")):
    email = email.strip()[:200]
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Email non valida.")
    vis, nuovo_qid = _visitatore(request)
    quote.registra_evento("lista_attesa", email=email, piano=piano[:30], note=note.strip()[:300], visitatore=vis)
    return _imposta_qid(JSONResponse({"ok": True, "messaggio": "Grazie! Ti scriviamo appena il piano è attivo, con uno sconto per chi si è iscritto prima."}), nuovo_qid)


@app.get("/api/admin/riepilogo")
def admin_riepilogo(chiave: str = ""):
    if not quote.ADMIN_KEY or chiave != quote.ADMIN_KEY:
        raise HTTPException(403, "Chiave non valida")
    return quote.riepilogo()

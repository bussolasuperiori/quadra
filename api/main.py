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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from engine import converti, to_csv, to_xlsx, Risultato
from engine.export import to_xlsx_multiplo

MAX_MB = int(os.environ.get("QUADRA_MAX_MB", "15"))
MAX_FILE = int(os.environ.get("QUADRA_MAX_FILES", "12"))
TTL_SEC = int(os.environ.get("QUADRA_TTL_SEC", "900"))        # 15 minuti
SEGNALAZIONI_DIR = Path(os.environ.get("QUADRA_SEGNALAZIONI", "/tmp/quadra_segnalazioni"))

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Quadra API", version="0.3.0")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

# token -> (timestamp, [(nome_file, Risultato), ...])
_cache: dict[str, tuple[float, list[tuple[str, Risultato]]]] = {}
_lock = threading.Lock()


def _pulisci():
    adesso = time.time()
    with _lock:
        for k in [k for k, (t, _) in _cache.items() if adesso - t > TTL_SEC]:
            _cache.pop(k, None)


@app.get("/", response_class=HTMLResponse)
def home():
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/commercialisti", response_class=HTMLResponse)
def commercialisti():
    return (WEB / "commercialisti.html").read_text(encoding="utf-8")


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


@app.post("/api/converti")
async def converti_pdf(file: list[UploadFile] = File(...)):
    """Accetta uno o più PDF. Risposta: un token unico + un risultato per file."""
    _pulisci()
    if not file:
        raise HTTPException(400, "Carica almeno un file PDF.")
    if len(file) > MAX_FILE:
        raise HTTPException(400, f"Massimo {MAX_FILE} file per volta.")
    risultati: list[tuple[str, Risultato]] = []
    for f in file:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, f"{f.filename or 'file'}: carica solo PDF.")
        dati = await f.read()
        risultati.append((Path(f.filename).stem, _converti_upload(dati, f.filename)))

    token = secrets.token_urlsafe(16)
    with _lock:
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
    return JSONResponse(corpo)


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
    return {"ok": True, "messaggio": "Grazie! Analizziamo il layout e ti scriviamo quando è supportato."}


@app.get("/campione.pdf")
def campione():
    p = Path(__file__).resolve().parent.parent / "tests" / "samples" / "reale_intesa_xme.pdf"
    if not p.exists():
        p = p.with_name("dare_avere.pdf")
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), media_type="application/pdf", filename="estratto_conto_esempio.pdf")

"""API Quadra — conversione estratti conto PDF.

Avvio locale:  uvicorn api.main:app --reload --port 8000
Privacy: il PDF viene scritto in un file temporaneo, analizzato e cancellato
subito; il risultato resta in memoria solo per il tempo di un download (TTL).
"""
from __future__ import annotations

import os
import secrets
import tempfile
import time
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from engine import converti, to_csv, to_xlsx, Risultato

MAX_MB = int(os.environ.get("QUADRA_MAX_MB", "15"))
TTL_SEC = int(os.environ.get("QUADRA_TTL_SEC", "900"))        # 15 minuti
LIMITE_GRATIS_RIGHE = int(os.environ.get("QUADRA_FREE_ROWS", "0"))  # 0 = nessun limite (MVP)

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Quadra API", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

_cache: dict[str, tuple[float, Risultato, str]] = {}
_lock = threading.Lock()


def _pulisci():
    adesso = time.time()
    with _lock:
        for k in [k for k, (t, _, _) in _cache.items() if adesso - t > TTL_SEC]:
            _cache.pop(k, None)


@app.get("/", response_class=HTMLResponse)
def home():
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"ok": True, "versione": app.version}


@app.post("/api/converti")
async def converti_pdf(file: UploadFile = File(...)):
    _pulisci()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Carica un file PDF.")
    dati = await file.read()
    if len(dati) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"Il file supera {MAX_MB} MB.")
    if not dati.startswith(b"%PDF"):
        raise HTTPException(400, "Il file non sembra un PDF valido.")

    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dati)
        try:
            ris = converti(tmp)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Non sono riuscito a leggere il PDF: {type(e).__name__}") from e
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    token = secrets.token_urlsafe(16)
    nome_base = Path(file.filename).stem
    with _lock:
        _cache[token] = (time.time(), ris, nome_base)
    corpo = ris.to_dict()
    corpo["token"] = token
    corpo["nome_file"] = nome_base
    return JSONResponse(corpo)


def _prendi(token: str) -> tuple[Risultato, str]:
    _pulisci()
    with _lock:
        voce = _cache.get(token)
    if not voce:
        raise HTTPException(404, "Risultato scaduto: ricarica il PDF.")
    return voce[1], voce[2]


@app.get("/api/scarica/{token}.xlsx")
def scarica_xlsx(token: str):
    ris, nome = _prendi(token)
    return Response(
        to_xlsx(ris),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}_quadra.xlsx"'},
    )


@app.get("/api/scarica/{token}.csv")
def scarica_csv(token: str):
    ris, nome = _prendi(token)
    return Response(
        ("﻿" + to_csv(ris)).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}_quadra.csv"'},
    )


@app.get("/campione.pdf")
def campione():
    p = Path(__file__).resolve().parent.parent / "tests" / "samples" / "dare_avere.pdf"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), media_type="application/pdf", filename="estratto_conto_esempio.pdf")

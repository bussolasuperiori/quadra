"""Quote del piano gratuito e registro eventi (lista d'attesa, segnalazioni, limiti raggiunti).

Senza account, il visitatore è identificato da un cookie anonimo (qid) e, in mancanza,
dall'hash dell'IP. Le pagine convertite nel mese vengono contate per visitatore.
Gli eventi finiscono in un file JSONL in QUADRA_DATA_DIR (su Render free il disco è
effimero: vanno letti periodicamente dall'endpoint admin o spostati su un webhook).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import urllib.request

DATA_DIR = Path(os.environ.get("QUADRA_DATA_DIR", "/tmp/quadra_data"))
FREE_PAGES = int(os.environ.get("QUADRA_FREE_PAGES", "30"))      # 0 = illimitato
WEBHOOK = os.environ.get("QUADRA_WEBHOOK_URL", "").strip()         # opzionale: POST JSON per ogni evento
ADMIN_KEY = os.environ.get("QUADRA_ADMIN_KEY", "").strip()

_lock = threading.Lock()
_uso: dict[str, dict[str, int]] = {}      # visitatore -> {"YYYY-MM": pagine}


def _file_uso() -> Path:
    return DATA_DIR / "uso.json"


def _file_eventi() -> Path:
    return DATA_DIR / "eventi.jsonl"


def _carica():
    global _uso
    try:
        _uso = json.loads(_file_uso().read_text())
    except Exception:  # noqa: BLE001
        _uso = {}


def _salva():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _file_uso().write_text(json.dumps(_uso))
    except Exception:  # noqa: BLE001
        pass


_carica()


def mese_corrente() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def id_visitatore(qid: Optional[str], ip: Optional[str]) -> str:
    if qid and len(qid) >= 16:
        return "c:" + qid[:64]
    return "ip:" + hashlib.sha256((ip or "?").encode()).hexdigest()[:24]


def pagine_usate(vis: str) -> int:
    with _lock:
        return _uso.get(vis, {}).get(mese_corrente(), 0)


def pagine_rimaste(vis: str) -> Optional[int]:
    if FREE_PAGES <= 0:
        return None
    return max(0, FREE_PAGES - pagine_usate(vis))


def consuma(vis: str, pagine: int) -> None:
    if FREE_PAGES <= 0:
        return
    with _lock:
        m = mese_corrente()
        d = _uso.setdefault(vis, {})
        # tieni solo il mese corrente
        for k in [k for k in d if k != m]:
            d.pop(k)
        d[m] = d.get(m, 0) + pagine
        _salva()


def registra_evento(tipo: str, **dati) -> None:
    ev = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tipo": tipo, **dati}
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _file_eventi().open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass
    print("EVENTO", json.dumps(ev, ensure_ascii=False), flush=True)   # finisce nei log di Render
    if WEBHOOK:
        threading.Thread(target=_invia_webhook, args=(ev,), daemon=True).start()


def _invia_webhook(ev: dict) -> None:
    try:
        req = urllib.request.Request(WEBHOOK, data=json.dumps(ev).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8).read()
    except Exception:  # noqa: BLE001
        pass


def leggi_eventi(limite: int = 500) -> list[dict]:
    try:
        righe = _file_eventi().read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in righe[-limite:]:
        try:
            out.append(json.loads(r))
        except Exception:  # noqa: BLE001
            continue
    return out


def riepilogo() -> dict:
    ev = leggi_eventi(5000)
    conteggi: dict[str, int] = {}
    for e in ev:
        conteggi[e.get("tipo", "?")] = conteggi.get(e.get("tipo", "?"), 0) + 1
    with _lock:
        visitatori_mese = sum(1 for d in _uso.values() if mese_corrente() in d)
        pagine_mese = sum(d.get(mese_corrente(), 0) for d in _uso.values())
    return {
        "mese": mese_corrente(),
        "visitatori_attivi": visitatori_mese,
        "pagine_convertite": pagine_mese,
        "eventi": conteggi,
        "lista_attesa": [e for e in ev if e.get("tipo") == "lista_attesa"][-100:],
        "segnalazioni": [e for e in ev if e.get("tipo") == "segnalazione"][-100:],
        "limiti_raggiunti": conteggi.get("limite", 0),
        "generato": time.time(),
    }

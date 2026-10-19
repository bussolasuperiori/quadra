# Quadra — estratto conto PDF → Excel

Converte gli estratti conto bancari italiani (PDF testuali) in Excel/CSV con:
- movimenti riconosciuti riga per riga (data, valuta, descrizione, importo con segno);
- categoria automatica per ogni movimento (regole trasparenti in `engine/categorie.py`);
- **controllo di quadratura**: saldo iniziale + movimenti = saldo finale;
- export Excel con formule, filtri e foglio di riepilogo per categoria.

## Struttura
```
engine/      motore (parser PDF, quadratura, categorie, export)
api/         FastAPI: POST /api/converti, GET /api/scarica/{token}.xlsx|csv
web/         landing page + interfaccia di conversione (un solo file HTML)
tests/       generatore di PDF sintetici + test end-to-end
docs/        checklist operativa e note
```

## Avvio locale
```bash
pip install -r requirements.txt
python -m tests.genera_campioni      # crea 3 estratti conto di prova in tests/samples/
python -m tests.test_parser          # deve stampare TOTALE ERRORI: 0
uvicorn api.main:app --reload        # http://localhost:8000
```

## Deploy
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/bussolasuperiori/quadra)

`render.yaml` è un blueprint per Render (piano gratuito, regione Francoforte).
In alternativa il `Dockerfile` funziona su Railway, Fly.io o qualsiasi VPS.

## Layout bancari verificati
| Banca | Layout | Metodo | Stato |
|---|---|---|---|
| Intesa Sanpaolo | XME Conto, estratto trimestrale (19 pagine, descrizioni multi-riga, cifre spezzate) | generico + colonne | quadra ✓ |
| Trade Republic | estratto riassuntivo (data su due righe, saldo progressivo) | template dedicato | quadra ✓ |
| Layout sintetici | Dare/Avere, importo con segno, saldo progressivo | generico | quadra ✓ |

I PDF in `tests/samples/reale_*.pdf` sono copie **anonimizzate** di estratti reali (nomi, IBAN, importi e saldi sostituiti con `tests/anonimizza.py`, quadratura ricalcolata).

## Privacy by design
- Il PDF viene salvato in un file temporaneo, letto e cancellato subito.
- Il risultato resta in memoria 15 minuti (TTL) solo per permettere il download.
- Nessun database, nessun log del contenuto.

## Roadmap tecnica
1. Raccogliere PDF reali anonimizzati e aggiungere template per banca (`engine/banche/`).
2. Account + crediti (Supabase) e pagamenti (Lemon Squeezy o Paddle).
3. Fallback AI per layout sconosciuti (testo estratto → movimenti strutturati).
4. OCR per PDF scansionati.
5. Export diretto su Google Sheets.

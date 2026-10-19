"""Pagine SEO per banca: /banche/<slug>.

Ogni pagina risponde alla ricerca "convertire estratto conto <banca> in excel" con contenuto
specifico (dove si scarica il PDF, cosa contiene, come lo legge Quadra) e porta alla home.
I testi evitano affermazioni non verificabili sui singoli layout: parlano del formato in generale
e dichiarano lo stato di supporto reale (verificato / in lavorazione).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Banca:
    slug: str
    nome: str
    stato: str            # "verificato" | "supporto generico"
    dove: str             # dove si scarica l'estratto conto in PDF
    nota_layout: str      # cosa ha di particolare il PDF
    tipo: str = "conto corrente"


BANCHE: list[Banca] = [
    Banca("intesa-sanpaolo", "Intesa Sanpaolo", "verificato",
          "dall'app Intesa Sanpaolo Mobile o dal sito, nella sezione Documenti → Estratti conto; l'estratto è trimestrale",
          "Estratto trimestrale di molte pagine, con colonne Data operazione / Data valuta / Descrizione / Addebiti / Accrediti; le descrizioni si estendono su più righe e alcune cifre sono spezzate da spazi. Verificato riga per riga su un estratto reale di 19 pagine: 196 movimenti, quadratura esatta."),
    Banca("unicredit", "UniCredit", "supporto generico",
          "dall'app UniCredit Mobile Banking o dalla banca via internet, sezione Documenti / Comunicazioni",
          "Estratto con colonne Data / Valuta / Descrizione / Entrate / Uscite e, in alcune versioni, saldo progressivo. Il parser generico riconosce questo schema; stiamo raccogliendo estratti reali per la verifica al centesimo."),
    Banca("bancoposta", "BancoPosta", "supporto generico",
          "dall'app BancoPosta o da poste.it, nella sezione Estratto conto / Lista movimenti (esportabile anche in PDF)",
          "Lista movimenti con data contabile, data valuta, descrizione e importo con segno oppure colonne Dare/Avere. Il parser generico gestisce entrambe le varianti."),
    Banca("fineco", "Fineco", "supporto generico",
          "dal sito Fineco, sezione Conto → Estratto conto, oppure dall'app",
          "Estratto con importi che riportano il segno davanti e saldo iniziale/finale in testa e in coda. Layout leggibile dal parser generico."),
    Banca("bper", "BPER Banca", "supporto generico",
          "dall'app BPER Banca o da Smart Web, sezione Documenti",
          "Colonne Data / Valuta / Dare / Avere / Descrizione: lo schema classico degli estratti conto italiani, riconosciuto dal parser generico."),
    Banca("banco-bpm", "Banco BPM", "supporto generico",
          "da YouWeb o dall'app YouApp, sezione Documenti → Estratti conto",
          "Schema Dare/Avere con descrizioni multi-riga, riconosciuto dal parser generico."),
    Banca("ing", "ING", "supporto generico",
          "dal sito ING, sezione Conto Arancio → Estratti conto, o dall'app",
          "Estratto con data, descrizione e importo con segno; saldi dichiarati in apertura e chiusura."),
    Banca("revolut", "Revolut", "supporto generico",
          "dall'app Revolut: Conto → Estratto conto → scegli periodo e formato PDF",
          "Estratto con colonne Data / Descrizione / Uscite / Entrate / Saldo, in italiano o inglese. Lo schema a colonne è riconosciuto dal parser generico."),
    Banca("n26", "N26", "supporto generico",
          "dall'app N26 o dal sito: Il mio conto → Estratti conto",
          "Estratto mensile con data, descrizione e importo con segno; saldo iniziale e finale dichiarati."),
    Banca("trade-republic", "Trade Republic", "verificato",
          "dall'app Trade Republic: Profilo → Documenti → Estratto conto",
          "Estratto riassuntivo con la data spezzata su due righe (\"16 set\" / \"2026\"), colonne IN ENTRATA / IN USCITA / SALDO e tabelle accessorie sui fondi monetari. Quadra ha un modello dedicato: verificato su un estratto reale, quadratura esatta."),
    Banca("credit-agricole", "Crédit Agricole Italia", "supporto generico",
          "dall'app Crédit Agricole o dal sito, sezione Documenti",
          "Schema Dare/Avere classico, riconosciuto dal parser generico."),
    Banca("mediolanum", "Banca Mediolanum", "supporto generico",
          "dal sito o dall'app Mediolanum, sezione Documenti → Estratti conto",
          "Schema a colonne con saldo iniziale e finale dichiarati, riconosciuto dal parser generico."),
]

PER_SLUG = {b.slug: b for b in BANCHE}


def _stato_html(b: Banca) -> str:
    if b.stato == "verificato":
        return '<span class="pill ok">✓ Verificato su estratti reali</span>'
    return '<span class="pill">Supporto generico · verifica in corso</span>'


def pagina_banca(b: Banca) -> str:
    altre = " · ".join(f'<a href="/banche/{x.slug}">{x.nome}</a>' for x in BANCHE if x.slug != b.slug)
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Convertire l'estratto conto {b.nome} da PDF a Excel — Quadra</title>
<meta name="description" content="Come trasformare l'estratto conto {b.nome} in PDF in un foglio Excel o CSV con i movimenti in tabella, le categorie e il controllo che i saldi tornino. Gratis per i primi estratti, senza registrazione.">
<link rel="canonical" href="https://quadra-mfai.onrender.com/banche/{b.slug}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#f6f7f9;--card:#fff;--ink:#15213a;--muted:#5b6478;--line:#e3e7ee;--blu:#1f3a5f;--blu-2:#2c5282;--verde:#1f7a4d;--verde-bg:#e7f5ec}}
  *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--ink);line-height:1.55}}
  header{{max-width:1040px;margin:0 auto;padding:22px 20px;display:flex;align-items:center;justify-content:space-between}}
  .logo{{display:flex;align-items:center;gap:10px;font-weight:700;font-size:20px;color:var(--ink);text-decoration:none}}
  .logo i{{width:28px;height:28px;border-radius:8px;background:var(--blu);display:inline-grid;place-items:center;color:#fff;font-style:normal;font-size:15px}}
  nav a{{color:var(--muted);text-decoration:none;margin-left:22px;font-size:15px}}
  main{{max-width:820px;margin:0 auto;padding:0 20px 80px}}
  h1{{font-size:clamp(28px,4.5vw,40px);line-height:1.12;letter-spacing:-.03em;margin:30px 0 10px}}
  h2{{font-size:22px;letter-spacing:-.02em;margin:40px 0 8px}}
  p,li{{color:#2b3550}} .muted{{color:var(--muted)}}
  .pill{{display:inline-block;font-size:13px;border-radius:999px;padding:5px 12px;background:#eef1f6;color:var(--muted);margin-bottom:10px}}
  .pill.ok{{background:var(--verde-bg);color:var(--verde)}}
  .btn{{display:inline-block;background:var(--blu);color:#fff;border-radius:10px;padding:12px 20px;font-weight:600;text-decoration:none}}
  .btn.sec{{background:#fff;color:var(--blu);border:1px solid var(--line)}}
  .box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}}
  ol li{{margin:6px 0}}
  .cta{{background:var(--blu);color:#fff;border-radius:14px;padding:26px;margin-top:40px;text-align:center}}
  .cta p{{color:#d6e0ee}} .cta .btn{{background:#fff;color:var(--blu)}}
  .altre{{font-size:14px;color:var(--muted);margin-top:30px;line-height:2}} .altre a{{color:var(--blu-2);text-decoration:none}}
  footer{{text-align:center;color:var(--muted);font-size:13px;padding:30px 20px;border-top:1px solid var(--line)}}
  @media (max-width:640px){{nav{{display:none}}}}
</style>
</head>
<body>
<header>
  <a class="logo" href="/"><i>Q</i> Quadra</a>
  <nav><a href="/#come">Come funziona</a><a href="/commercialisti">Per studi</a><a href="/#prezzi">Prezzi</a><a href="/#faq">Privacy</a></nav>
</header>
<main>
  {_stato_html(b)}
  <h1>Convertire l'estratto conto {b.nome} da PDF a Excel</h1>
  <p class="muted">Carica il PDF dell'estratto conto {b.nome} e ottieni i movimenti in tabella, con categoria e controllo di quadratura. Gratis per i primi estratti, senza registrazione.</p>
  <p style="margin:18px 0 6px"><a class="btn" href="/?banca={b.slug}">Converti il tuo estratto {b.nome}</a> &nbsp; <a class="btn sec" href="/campione.pdf" download>Prova con un esempio</a></p>

  <h2>Dove trovi l'estratto conto in PDF</h2>
  <p>Di norma {b.dove}. Serve il PDF generato dalla banca (quello in cui riesci a selezionare il testo), non una foto o una scansione.</p>

  <h2>Com'è fatto il PDF {b.nome} e come lo legge Quadra</h2>
  <div class="box"><p style="margin:0">{b.nota_layout}</p></div>
  <p>Quadra riconosce la tabella dei movimenti, riunisce le descrizioni che vanno a capo, assegna una categoria a ogni riga (utenze, carburante, bonifici, commissioni, tasse…) e poi verifica che <strong>saldo iniziale + movimenti = saldo finale</strong>. Se i due numeri non coincidono, lo vedi subito con la differenza esatta.</p>

  <h2>Come si fa, in tre passaggi</h2>
  <ol>
    <li>Scarica l'estratto conto {b.nome} in PDF dall'home banking.</li>
    <li>Trascinalo sulla <a href="/?banca={b.slug}">home di Quadra</a>: in pochi secondi vedi l'anteprima dei movimenti e la riga di quadratura.</li>
    <li>Scarica l'Excel (con filtri, totali e riepilogo per categoria) o il CSV per il gestionale. Puoi caricare più estratti insieme e ottenere un file unico.</li>
  </ol>

  <h2>Cosa ottieni nel file Excel</h2>
  <ul>
    <li>Colonne Data, Data valuta, Descrizione, Categoria, Entrate, Uscite, Importo</li>
    <li>Totali con formule, filtri attivi, un foglio di riepilogo per categoria</li>
    <li>Con più estratti: un foglio "Tutti i movimenti" e uno per ogni file</li>
    <li>CSV con punto e virgola e decimali italiani, pronto per l'import</li>
  </ul>

  <h2>Privacy</h2>
  <p>Il PDF viene elaborato in memoria e cancellato subito dopo la conversione; il risultato resta scaricabile per 15 minuti e poi sparisce. Server in Europa, nessun archivio.</p>

  <h2>Domande frequenti</h2>
  <div class="box"><strong>Il mio estratto {b.nome} non viene letto bene.</strong><p style="margin:6px 0 0">Dopo la conversione trovi il pulsante "Segnalaci il layout": ci mandi il PDF (puoi oscurare nome e IBAN) e aggiungiamo il modello della banca in pochi giorni, avvisandoti via email.</p></div>
  <div class="box"><strong>Funziona anche con la carta di credito o il conto deposito {b.nome}?</strong><p style="margin:6px 0 0">Se l'estratto ha una tabella di movimenti con date e importi, nella maggior parte dei casi sì. Provalo: la prova non richiede registrazione.</p></div>
  <div class="box"><strong>Quanto costa?</strong><p style="margin:6px 0 0">30 pagine al mese sono gratis. Oltre, i piani partono da 9 €/mese. Dettagli nella <a href="/#prezzi">pagina prezzi</a>.</p></div>

  <section class="cta">
    <h2 style="margin:0 0 6px;color:#fff">Prova subito con il tuo estratto {b.nome}</h2>
    <p>Nessuna registrazione, risultato in pochi secondi.</p>
    <a class="btn" href="/?banca={b.slug}">Converti in Excel</a>
  </section>

  <p class="altre"><strong>Altre banche:</strong> {altre}</p>
</main>
<footer>Quadra · Estratti conto PDF → Excel con quadratura · <a href="mailto:ciao@quadra.app" style="color:var(--muted)">ciao@quadra.app</a></footer>
</body>
</html>"""


def pagina_indice() -> str:
    righe = "".join(
        f'<li><a href="/banche/{b.slug}">{b.nome}</a> — {"verificato su estratti reali" if b.stato == "verificato" else "supporto generico"}</li>'
        for b in BANCHE
    )
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Banche supportate — Quadra</title><meta name="description" content="Elenco delle banche italiane i cui estratti conto PDF si convertono in Excel con Quadra.">
<link rel="canonical" href="https://quadra-mfai.onrender.com/banche">
<style>body{{font-family:Inter,system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;color:#15213a;line-height:1.6}} a{{color:#2c5282}} li{{margin:6px 0}}</style></head>
<body><p><a href="/">← Quadra</a></p><h1>Banche supportate</h1>
<p>Il motore riconosce lo schema a colonne usato dalla maggior parte degli estratti conto italiani. Per alcune banche abbiamo verificato riga per riga su estratti reali.</p>
<ul>{righe}</ul>
<p>La tua banca non c'è? Prova comunque sulla <a href="/">home</a>: se il layout non viene letto, segnalacelo e lo aggiungiamo.</p></body></html>"""


def sitemap(base: str) -> str:
    urls = [f"{base}/", f"{base}/commercialisti", f"{base}/banche"] + [f"{base}/banche/{b.slug}" for b in BANCHE]
    corpo = "".join(f"<url><loc>{u}</loc><changefreq>weekly</changefreq></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{corpo}</urlset>'

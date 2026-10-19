# Piano di sponsorizzazione Quadra — "non faccio troppo io"

Obiettivo: capire in 30 giorni, con 150–300 €, se qualcuno vuole pagare per Quadra, senza vendere di persona.
Il sito fa tutto da solo: converte gratis, blocca a 30 pagine/mese, raccoglie le email di chi vuole di più.
**La metrica che conta è una sola: iscritti alla lista d'attesa** (chi lascia l'email dopo aver toccato il limite o
visto il prezzo). 10+ email in un mese = c'è domanda, si attivano i pagamenti. 0–2 = si cambia idea, spendendo poco.

## Perché Google Ads e non Meta
Chi cerca "convertire estratto conto pdf in excel" ha il problema *adesso*: la conversione è immediata.
Su Instagram/Facebook nessuno sta pensando a un estratto conto. Google Ads è l'unico canale sensato all'inizio.

## Struttura campagna (Ricerca, solo Italia, italiano)

**Campagna 1 — Problema generico** (budget 5 €/giorno)
Gruppo "estratto conto excel":
- `estratto conto pdf excel`
- `convertire estratto conto in excel`
- `estratto conto da pdf a excel`
- `trasformare estratto conto in excel`
- `estratto conto csv`
- `importare estratto conto in excel`
- `movimenti bancari pdf excel`
Tipo di corrispondenza: **a frase** ("…") per tutte. Niente corrispondenza generica.

**Campagna 2 — Per banca** (budget 3 €/giorno)
Un gruppo per banca, parola chiave a frase `estratto conto <banca> excel`, `estratto conto <banca> pdf`
per: Intesa Sanpaolo, UniCredit, BancoPosta, Fineco, Revolut, N26. Pagina di destinazione: `/banche/<slug>`.

**Campagna 3 — Studi** (budget 2 €/giorno, opzionale dopo 2 settimane)
`riconciliazione bancaria excel`, `riconciliazione estratto conto`, `software riconciliazione bancaria`.
Destinazione: `/commercialisti`.

**Parole chiave escluse (negative)**, a livello account: `gratis`, `free`, `modello`, `fac simile`, `template`,
`come leggere`, `cos'è`, `significato`, `lavoro`, `stipendio`, `calcolo`, `app banca`, `accedere`, `login`.

## Annunci (responsive, 3 titoli + 2 descrizioni; Google li combina)
Titoli (max 30 caratteri):
1. Estratto conto PDF in Excel
2. Movimenti in tabella in 10 s
3. Con controllo di quadratura
4. Gratis per 30 pagine al mese
5. Banche italiane supportate
6. Nessuna registrazione
7. Più PDF, un solo Excel
8. File cancellati subito
Descrizioni (max 90 caratteri):
1. Carica il PDF della banca, ottieni Excel o CSV con categorie e saldi verificati. Prova gratis.
2. Intesa, UniCredit, BancoPosta, Fineco, Revolut e altre. Server in Europa, privacy garantita.
3. Per studi e piccole imprese: riconciliazione senza ricopiare. Più estratti in un file unico.
URL finale: https://quadra-mfai.onrender.com (campagna 1), /banche/<slug> (campagna 2), /commercialisti (campagna 3).

## Conversioni da misurare (già pronte nel sito)
| Evento | Quando scatta | Valore |
|---|---|---|
| `conversione_ok` | un PDF convertito con successo | conversione primaria (azione Ads) |
| `download` | click su Excel/CSV | secondaria |
| `lista_attesa` | email lasciata | **quella che decide** |
| `limite_raggiunto` | visitatore oltre 30 pagine | segnale di intensità d'uso |
| `da_pagina_banca` | arrivo dalle pagine SEO | attribuzione |
Il sito invia questi eventi a Google solo se è impostata la variabile `QUADRA_GTAG_ID` (vedi sotto).

## Budget e aspettative realistiche
- 10 €/giorno totali ≈ 300 €/mese. CPC atteso 0,30–1,00 € → 300–900 clic/mese.
- Se il 20% converte un PDF e il 5% di questi lascia l'email: 3–9 email/mese. È il numero da battere.
- Primi 7 giorni: non toccare nulla. Giorni 8–14: spegnere le parole chiave con 0 conversioni e >15 clic.

## Cosa devi fare tu (una volta sola, ~30 minuti)
1. **Render → piano Starter** (7 $/mese): con il piano gratuito il sito dorme e il primo clic da un annuncio aspetta 40 s.
   Pagare clic per far vedere una pagina di caricamento è buttare soldi. Dashboard Render → quadra → Settings → Instance type.
2. **Account Google Ads** su ads.google.com con il tuo Google. Salta la "campagna guidata": scegli modalità esperto.
   Metodo di pagamento: carta.
3. **Crea l'azione di conversione** (Obiettivi → Conversioni → Nuova → Sito web → "aggiungi manualmente"):
   nome `Conversione PDF`, categoria Lead, conteggio "uno per click". Google ti mostra un ID tipo `AW-123456789`
   e un'etichetta tipo `AW-123456789/AbCdEfGh`.
4. **Incolla i due valori su Render**: Dashboard → quadra → Environment → aggiungi `QUADRA_GTAG_ID` = `AW-…`
   e `QUADRA_ADS_CONVERSION` = `AW-…/…`. Salva: il sito si riavvia con il tracciamento attivo. Non serve toccare il codice.
5. **Crea le campagne** come descritte sopra (copia/incolla titoli e descrizioni). Imposta la lingua italiano,
   località Italia, rete solo Ricerca (togli "partner di ricerca" e "Display").
6. **Google Search Console** (search.google.com/search-console): aggiungi `quadra-mfai.onrender.com`,
   verifica con il metodo "tag HTML" (dammi il codice e lo inserisco) e invia la sitemap `/sitemap.xml`.
   È gratis e porta traffico organico dalle pagine per banca nel giro di 1–2 mesi.

## Cosa faccio io
- Ogni settimana leggo il riepilogo (`/api/admin/riepilogo?chiave=…`, la chiave è su Render → Environment):
  conversioni, pagine, email in lista d'attesa, segnalazioni di banche non lette.
- Ti mando un messaggio con tre numeri: clic (da Ads), PDF convertiti, email raccolte. E una decisione proposta.
- Se arrivano segnalazioni di layout, aggiungo i template senza chiederti nulla.
- Quando le email in lista superano 10: preparo pagamenti (Lemon Squeezy) e account, e ti chiedo la P.IVA.

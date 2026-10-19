"""Categorizzazione dei movimenti tramite regole (parole chiave).

Le regole sono volutamente semplici e trasparenti: l'utente deve capire perché
un movimento è finito in una categoria e poterla correggere. Una fase AI
opzionale potrà occuparsi dei casi non coperti.
"""
from __future__ import annotations

import re
from .models import Movimento

# ordine = priorità (la prima regola che combacia vince)
REGOLE: list[tuple[str, str]] = [
    ("Investimenti", r"buy\s+trade|sell\s+trade|savings\s+plan|dividend|stamp\s+duty|\bisin\b|acquisto\s+titoli|vendita\s+titoli|sottoscrizione\s+fondo|\betf\b|obbligaz|cedol|piano\s+di\s+accumulo|\bpac\b|deposito\s+titoli|trading|q\.ta'|id\.op\.|per\s+investimenti"),
    ("Tasse e tributi", r"\bf24\b|agenzia\s+entrate|imposta\s+di\s+bollo|\bbollo\b|\btari\b|\bimu\b|\birpef\b|\biva\b|inps|inail|tributi|pagopa|cbill"),
    ("Prelievo contanti", r"prelievo|prelevamento|\batm\b.*(?:prel|cash|contant)|bancomat.*prel|prel.*\batm\b"),
    ("Stipendio / Entrate lavoro", r"stipend|emolument|competenze\s+mese|retribuz|pensione|cedolino|compenso|fattura\s+n|parcella"),
    ("Bonifici in entrata", r"bonifico\s+(?:a\s+vostro\s+favore|ricevuto|in\s+entrata|da)|accredito\s+bonifico|giroconto\s+in\s+entrata"),
    ("Bonifici in uscita", r"bonifico\s+(?:a\s+favore|disposto|in\s+uscita|verso|sepa)|disposizione\s+di\s+bonifico|giroconto"),
    ("Commissioni e spese bancarie", r"commission|canone|spese\s+(?:tenuta|conto|gestione|invio|liquidazione)|competenze\s+e\s+spese|diritti\s+di|bollo\s+conto"),
    ("Utenze", r"enel|eni\s*plenitude|\bhera\b|\ba2a\b|iren|edison|sorgenia|acea|fastweb|\btim\b|vodafone|wind|iliad|telecom|\bgas\b|\bluce\b|\bacqua\b|\benergia\b|\bopen\s*fiber"),
    ("Affitto / Mutuo / Prestiti", r"affitto|canone\s+di\s+locazione|locazione|rata\s+mutuo|mutuo|finanziamento|rata\s+prestito|prestito|rata\s+macchina|rateale"),
    ("Assicurazioni", r"assicuraz|polizza|generali|unipol|allianz|axa\b|\bzurich|genertel|verti|prima\s+assicurazioni"),
    ("Carburante", r"\beni\s+station|\bq8\b|\bip\s+(?:matic|station|carb)|\besso\b|\btamoil\b|\bshell\b|carburant|benzin|distributore|\bagip\b|total\s*erg|\bstazione\s+di\s+servizio"),
    ("Trasporti", r"trenitalia|italo|atm\s+milano|atm\s+servizi|trenord|autostrad|telepass|parcheggio|parking|uber|bolt|taxi|ryanair|easyjet|ita\s+airways|wizz|flixbus"),
    ("Spesa alimentare", r"esselunga|coop\b|conad|carrefour|lidl|eurospin|iper\b|pam\b|despar|md\s+discount|aldi|penny|bennet|tigros|il\s+gigante|supermerc|alimentar|famila|crai\b"),
    ("Ristoranti e bar", r"ristorante|pizzeria|trattoria|osteria|bar\b|caff[eè]|mcdonald|burger|kfc|deliveroo|glovo|just\s*eat|sushi|kebab|pub\b|gelateria|pasticceria"),
    ("Farmacia e salute", r"farmacia|parafarmacia|ospedale|asl\b|ats\b|ticket|medic|dentist|ottic|analisi|clinica|poliambulatorio"),
    ("Abbonamenti e digitale", r"netflix|spotify|amazon\s+prime|prime\s+video|disney|dazn|apple\.com|itunes|google\s*(?:play|one|storage)|microsoft|adobe|dropbox|icloud|youtube|now\s*tv|sky\b|chatgpt|openai|anthropic|canva|notion"),
    ("Shopping online", r"amazon|ebay|zalando|aliexpress|shein|temu|vinted|subito\.it|paypal|wish\b|etsy"),
    ("Abbigliamento", r"zara|h&m|\bhm\b|oviesse|ovs\b|decathlon|primark|uniqlo|nike|adidas|bershka|pull&bear|calzedonia|intimissimi|tezenis|piazza\s+italia"),
    ("Casa e arredo", r"ikea|leroy\s*merlin|brico|obi\b|mondo\s+convenienza|maisons\s+du\s+monde|tiger|kasanova|bricocenter|ferramenta"),
    ("Elettronica", r"mediaworld|unieuro|euronics|expert|trony|apple\s+store|samsung"),
    ("Sport e tempo libero", r"palestra|gym|fitness|piscina|decathlon|cinema|teatro|concerto|ticketone|museo|libreria|feltrinelli|mondadori|giunti"),
    ("Istruzione", r"scuola|universit|istituto|retta|mensa\s+scolastica|corso\s+di|asilo|nido\b|libri\s+di\s+testo"),
    ("Versamento contanti", r"versamento\s+contant|versamento\s+assegn|versamento"),
    ("Pagamento POS / carta", r"\bpos\b|pagamento\s+carta|pagamento\s+tramite\s+pos|addebito\s+carta|carta\s+di\s+(?:credito|debito)|operazione\s+carta"),
    ("Addebiti ricorrenti (SDD/RID)", r"\bsdd\b|\brid\b|\badue\b|addebito\s+diretto|domiciliaz|utenza"),
    ("Carta di credito", r"saldo\s+e/c\s+carta|estratto\s+conto\s+carta|addebito\s+carta\s+di\s+credito"),
    ("Interessi", r"interess|interest\s+payment|competenze\s+(?:credit|debit)"),
    ("Donazioni", r"donazion|offerta|beneficenza|onlus|emergency|unicef|airc|caritas"),
]

_COMPILATE = [(nome, re.compile(pat, re.IGNORECASE)) for nome, pat in REGOLE]


def categoria_di(descrizione: str, importo) -> str:
    d = descrizione.lower()
    for nome, rx in _COMPILATE:
        if rx.search(d):
            # qualche correzione in base al segno
            if nome == "Bonifici in uscita" and importo > 0:
                return "Bonifici in entrata"
            if nome == "Bonifici in entrata" and importo < 0:
                return "Bonifici in uscita"
            return nome
    return "Altre entrate" if importo > 0 else "Altre uscite"


def categorizza(movimenti: list[Movimento]) -> None:
    for m in movimenti:
        m.categoria = categoria_di(m.descrizione, m.importo)

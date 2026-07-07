# cassazione-penale-db

**Banca dati aperta di giurisprudenza penale con fonti verificabili**: le pronunce penali
segnalate dall'Ufficio del Massimario della Corte Suprema di Cassazione, l'**archivio completo
della Corte costituzionale dal 1956** (open data ufficiale) e il radar del merito dalle riviste
open access.

> *Nota sul nome*: il repository è nato per le sole segnalate della Cassazione e ne conserva
> il nome; il perimetro si è esteso (Corte costituzionale, merito). Un'eventuale ridenominazione
> è rinviata a valle dei test in corso per non rompere le integrazioni esistenti.

Una scheda Markdown per pronuncia: massima ufficiale (campo "Oggetto"), "L'esito in sintesi",
estremi completi e link diretto alla scheda ufficiale e al PDF autentico sul sito della Corte.
**Nessuna riformulazione**: solo testo ufficiale, verificabile con un clic.

## Perimetro

**Incluso** — le pronunce che l'Ufficio del Massimario pubblica sulla pagina
["Giurisprudenza Penale"](https://www.cortedicassazione.it/it/giurisprudenza_penale.page)
del sito della Corte (3–5 a settimana, di rilievo nomofilattico):
sentenze e ordinanze di sezione segnalate, sentenze delle Sezioni Unite,
questioni rimesse alle Sezioni Unite (pendenti e decise).

**Escluso** — le circa 450 pronunce ordinarie settimanali non segnalate,
i provvedimenti di restituzione, il testo integrale dei provvedimenti
(linkato in ogni scheda, non copiato).

## Struttura

```
SEGNALATE/
├── 2026/                  ← una scheda per pronuncia, struttura piatta per anno
│   ├── Cass_23006_2026.md      (sentenze/ordinanze; prefisso SU_ per le Sezioni Unite)
│   └── QSP_9916_2026.md        (questioni SU; lo stato pendente/decisa è nel frontmatter)
├── INDICE.md              ← indice per materia + registro numero→scheda
├── RASSEGNE.md            ← link alle Rassegne mensili del Massimario
└── LOG_ERRORI.md          ← anomalie della pipeline (mai contenuti inventati)
```

Il formato delle schede è definito in [`SPEC_SCHEDA.md`](SPEC_SCHEDA.md).

## Corte costituzionale (open data ufficiale)

In `CONSULTA/` **tutte** le pronunce della Corte costituzionale dal 1956 a oggi (oltre 22.000), costruite dal
**servizio open data ufficiale** della Consulta ([dati.cortecostituzionale.it](https://dati.cortecostituzionale.it/),
licenza CC BY-SA 3.0, aggiornamento settimanale): per ogni pronuncia, **dispositivo
integrale**, **massime ufficiali** con i parametri normativi strutturati e link alla
scheda ufficiale. Le schede NON contengono epigrafe né testo integrale (riportano i
dati delle parti dei giudizi a quo): per il testo completo si segue il link.
Quando le massime di una pronuncia recente vengono pubblicate, la scheda si
aggiorna da sola alla run successiva.

## Radar del merito (segnalazioni, non citazioni)

In `SEGNALATE/RADAR/RADAR_MERITO.md` la pipeline raccoglie ogni settimana le **segnalazioni
di giurisprudenza di merito** pubblicate da riviste scientifiche open access (v1: l'Osservatorio
della giurisprudenza di merito di *Sistema Penale* e il feed di *Giurisprudenza Penale*).

Regole: si raccolgono **solo i fatti** — data, fonte, titolo, link — mai i contenuti redazionali,
che restano degli editori (Sistema Penale è CC BY-NC-ND). Il radar è **materiale informativo,
non citabile negli atti**: per usare un provvedimento segnalato, si apre il link, si scarica il
PDF del provvedimento (atto pubblico) e lo si ingerisce nella propria KB. Dedup per URL.

## Aggiornamento

Automatico, **settimanale**, via GitHub Action (in attivazione — vedi roadmap).
Ogni scheda riporta nel frontmatter la data di estrazione (`estratto_il`).
Principio vincolante: se la fonte non risponde o la struttura della pagina è cambiata,
la pipeline **non inventa nulla** — registra l'anomalia in `LOG_ERRORI.md` e si ferma.

## Regole dei dati

- Ogni campo proviene dalla pagina ufficiale della Corte ed è copiato **testualmente**;
  un campo assente alla fonte resta `null`, mai completato.
- **Nessun dato personale delle parti** (minimizzazione): il campo "Ricorrente" esposto
  dalla Corte non viene estratto. Presidente e relatore sì (magistrati nell'esercizio
  di funzione pubblica).
- Deduplicazione per chiave `(tipo, numero/R.G., anno)`; schede incomplete in quarantena,
  mai pubblicate.

## Uso con il Kit Penalista Italia

Questo repo è la sorgente dati del sistema di grounding giurisprudenziale del
[Kit Penalista Italia](https://github.com/Synthos-Logic/penalista-italia):
le schede si montano in `KNOWLEDGE_BASE/02_GIURISPRUDENZA/SEGNALATE/` e ogni citazione
prodotta dal kit porta il riferimento alla scheda e al PDF ufficiale (quote-then-claim).
Il repo resta comunque utilizzabile da chiunque, anche senza il kit.

## Note legali e licenze

- I testi dei provvedimenti e delle massime sono **atti ufficiali dello Stato**
  (art. 5 l. 633/1941): non soggetti a diritto d'autore. La fonte autentica è il sito
  della Corte di Cassazione, linkato in ogni scheda.
- **Schede e banca dati**: licenza [CC BY 4.0](LICENSE-SCHEDE.md) — riuso libero con attribuzione.
- **Script**: licenza [MIT](LICENSE).
- Materiale di lavoro professionale: la verifica finale sulla fonte ufficiale resta
  responsabilità del professionista.

## Roadmap

- [x] Specifica del formato scheda + prime schede validate
- [x] Pipeline di estrazione (`scripts/aggiorna_banca_dati.py`)
- [x] GitHub Action settimanale (`.github/workflows/aggiorna.yml`) — verifica mensile Rassegne: prossima
- [x] Radar del merito dalle riviste open access (`SEGNALATE/RADAR/`)
- [x] Backfill dello storico completo (295 schede: sentenze dal 2024, questioni SU dal 2023)
- [x] Fonte Corte costituzionale via open data ufficiale (`CONSULTA/`, archivio completo 1956-oggi: 22.357 pronunce con dispositivi e massime)
- [ ] Repo gemello per il civile (stessa specifica)

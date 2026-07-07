# cassazione-penale-db

**Banca dati aperta delle pronunce penali segnalate dall'Ufficio del Massimario della Corte Suprema di Cassazione.**

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
- [ ] Pipeline di estrazione (`scripts/`)
- [ ] GitHub Action settimanale + verifica mensile Rassegne
- [ ] Backfill dello storico disponibile sulla pagina della Corte
- [ ] Repo gemello per il civile (stessa specifica)

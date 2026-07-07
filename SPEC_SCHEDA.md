# SPEC — Formato scheda "Pronunce segnalate" Cassazione penale
*Versione 1.0 — 6 luglio 2026 — specifica ufficiale del formato dati di questo repository*

## Decisioni strutturali (prese il 06/07/2026)

| # | Decisione | Scelta |
|---|---|---|
| D1 | Montaggio nella KB utente | `KNOWLEDGE_BASE/02_GIURISPRUDENZA/SEGNALATE/` — contenuti nella zona giurisprudenza, in `_INDICE/` solo gli artefatti d'indice |
| D2 | Granularità REGISTRO_FONTI | Una riga per collezione/anno (es. "Pronunce segnalate 2026"); il lookup per singola pronuncia sta nel registro citazionale dell'INDICE |
| D3 | Testo integrale | NO — scheda leggera: massima ufficiale + esito in sintesi + link al PDF autentico della Corte. Integrazione on-demand su richiesta dell'avvocato |

## Principi (il nostro percorso)

1. **La scheda è una fonte del sistema di grounding**, non un file a sé: nasce già registrata (manifest) e indicizzata (registro citazionale). Tipo fonte: `massimario-segnalate`.
2. **Solo dati della Corte, testuali.** Ogni campo proviene dalla pagina ufficiale di dettaglio; nessuna riformulazione, nessun completamento. Campo assente alla fonte = campo `null`, mai inventato.
3. **Niente dati personali delle parti.** Il campo "Ricorrente" esposto dalla Corte NON viene estratto (minimizzazione, repo pubblico). Presidente e relatore sì: magistrati nell'esercizio di funzione pubblica.
4. **Nomi file stabili.** Lo stato di una questione SU (pendente → decisa) cambia nel frontmatter, non nel nome del file: i link non si rompono mai.
5. **Struttura piatta per anno.** Niente cartelle per materia: la materia è nel frontmatter e il raggruppamento lo fanno gli indici (regola wikilinks del kit: gli indici li mantiene Claude, l'avvocato non naviga cartelle). Il parser non deve mai creare/scegliere cartelle: meno logica, meno rotture.

## Struttura nel repo dati

```
SEGNALATE/
├── 2026/
│   ├── Cass_23006_2026.md          ← sentenze e ordinanze (prefisso SU_ per Sezioni Unite)
│   ├── SU_21077_2026.md
│   └── QSP_9916_2026.md            ← questioni SU (stato nel frontmatter)
├── manifest.json                    ← manifest collezioni (schema compatibile *.index.json)
├── INDICE.md                        ← indice generale: per materia e per numero
├── RASSEGNE.md                      ← link alle Rassegne mensili del Massimario
└── LOG_ERRORI.md
```

Anno di appartenenza = anno del numero della pronuncia (o dell'R.G. per le questioni).

## Formato scheda — SENTENZA / ORDINANZA

```markdown
---
tipo: sentenza                  # sentenza | ordinanza
sezione: "Terza"                # Prima…Settima | "Sezioni Unite"
numero: 23006
anno: 2026
data_udienza: 2026-06-11
data_deposito: 2026-06-22
data_inserimento: 2026-06-23    # data pubblicazione sulla pagina della Corte
materia: "Impugnazioni"         # tassonomia della Corte, testuale
presidente: "L. Ramacci"
relatore: "A. Scarcella"
rv: null                        # numero CED quando disponibile → raccordo col massimario annuale
content_id: "SZP51164"
url_scheda: "https://www.cortedicassazione.it/it/penale_dettaglio.page?contentId=SZP51164"
url_pdf: "https://www.cortedicassazione.it/resources/cms/documents/23006_06_2026_pen_noindex.pdf"
fonte: massimario-segnalate
estratto_il: 2026-07-06
---

# Cass. pen., Sez. III, n. 23006/2026

## Massima ufficiale (Oggetto)
> [testo integrale del campo "Oggetto", tra virgolette di citazione]

## L'esito in sintesi
[testo integrale del campo "L'esito in sintesi", senza riformulazioni]

## Fonte autentica
- Scheda ufficiale: [url_scheda]
- PDF del provvedimento: [url_pdf]
```

## Formato scheda — QUESTIONE SEZIONI UNITE

Differenze: `tipo: questione-su`, `stato: pendente | decisa`, `rg: "9916/2026"` al posto di numero/anno di sentenza (numero anno derivati dall'R.G.), campo `quesito` nel corpo (testo integrale), `riferimenti_normativi` nel corpo, `ordinanza_rimessione` (numero + URL PDF) in frontmatter, `decisa_da: null` → riferimento alla scheda della sentenza SU quando decisa. Niente campo ricorrente (principio 3).

Ciclo di vita: alla decisione, la pipeline aggiorna `stato: decisa` + `decisa_da: "SU_NUMERO_ANNO"` e crea la scheda della sentenza SU. Il file non viene mai rinominato.

## Integrazione col sistema di grounding (kit v3.3.x)

### REGISTRO_FONTI.md — una riga per collezione/anno (D2)
```
| Pronunce segnalate Massimario 2026 | massimario-segnalate | — | 87 schede | `02_GIURISPRUDENZA/SEGNALATE/2026/` |
```

### INDICE.md — nuova sezione del registro citazionale
Accanto all'attuale "2. Registro citazionale (Rv → fonte : pagina → massima)" si aggiunge:
```
## 3. Registro segnalate (numero/anno → scheda)
- Cass. Sez. III n. 23006/2026 · Impugnazioni · dep. 22/06/2026 → `SEGNALATE/2026/Cass_23006_2026.md`
- Cass. SU n. 21077/2026 · Misure di prevenzione · dep. 08/06/2026 → `SEGNALATE/2026/SU_21077_2026.md`
- QSP R.G. 9916/2026 · PENDENTE · ud. 29/10/2026 → `SEGNALATE/2026/QSP_9916_2026.md`
```

### Toolchain
`aggiorna_indice.py` oggi indicizza solo PDF. Serve un adattatore (`indicizza_schede.py`, nuovo script di `penalista-archivio`, ~Fase 5) che legga `SEGNALATE/manifest.json` e produca l'entry compatibile per il generatore dell'INDICE master. Il manifest lo produce la pipeline nel repo dati: il kit non deve mai parsare le schede una a una.

### Procedura di citazione (estensione del PROTOCOLLO_GROUNDING)
1. Cerca nel registro segnalate (numero o materia) → apri la scheda → **incolla la massima testuale**.
2. Formato citazione: `Cass. pen., Sez. III, n. 23006 del 2026 (dep. 22/06/2026) — massima ufficiale segnalata dall'Ufficio del Massimario (scheda in KB + PDF ufficiale: url_pdf)`.
3. Il testo integrale NON è in KB (D3): per affermazioni che richiedono il testo pieno → "testo integrale non in KB", rinvio al PDF ufficiale, integrazione on-demand.
4. Quando la pronuncia comparirà nel massimario annuale con Rv, il campo `rv` viene valorizzato: da quel momento la citazione preferisce il riferimento Rv (fonte consolidata), la scheda resta come fonte rapida.

### Gerarchia (GERARCHIA_FONTI.md)
- `massimario-segnalate` con `sezione: Sezioni Unite` → **LIVELLO 1**.
- `massimario-segnalate` sezioni semplici → **LIVELLO 2** (come le Rassegne del Massimario: rappresentazione ufficiale, non sostitutiva della sentenza).
- Le questioni SU pendenti non sono precedenti: citabili solo come "questione rimessa alle SU, udienza fissata al …" (utilissime in strategia difensiva, mai come autorità).

## Regole di estrazione (vincolanti per il parser — Fase 2)

1. Ogni campo obbligatorio (tipo, sezione, numero/rg, anno, materia, massima, url_pdf) assente o malformato → scheda in `_QUARANTENA/` + riga in LOG_ERRORI.md. Mai pubblicare schede incomplete, mai completare.
2. Testi copiati verbatim (massima, esito, quesito): nessuna normalizzazione oltre a spazi/entità HTML.
3. Dedup per chiave `(tipo, numero|rg, anno)`.
4. Esclusi: Provvedimenti di restituzione; campo Ricorrente.

## Esempi validati (schede reali estratte il 06/07/2026)
- `SEGNALATE/2026/Cass_23006_2026.md` — sentenza, Sez. III, materia Impugnazioni
- `SEGNALATE/2026/QSP_9916_2026.md` — questione SU pendente, ud. 29/10/2026

## Addendum — Schede CONSULTA (Corte costituzionale)

Fonte: **open data ufficiale** (dati.cortecostituzionale.it, CC BY-SA 3.0), non scraping.
Struttura: `CONSULTA/<anno>/{S|O}_<numero>_<anno>.md` — frontmatter con estremi, tipologia di
giudizio, `n_massime` (chiave dell'auto-aggiornamento: la scheda viene rigenerata quando la
Corte pubblica nuove massime) e `url_scheda`; corpo con **dispositivo integrale**, **massime
ufficiali** con parametri normativi strutturati e fonte autentica. **Esclusi epigrafe e testo
integrale** (contengono i dati delle parti dei giudizi a quo): per il testo completo si segue
il link ufficiale. Nessun filtro di materia: tutte le pronunce, grep-abili per norma
(es. `cod. pen.`, `131-bis`). Copertura: 1956 → oggi, retrieve iniziale una tantum +
incrementi settimanali.

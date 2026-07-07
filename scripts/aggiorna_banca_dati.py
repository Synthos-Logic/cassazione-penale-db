#!/usr/bin/env python3
"""
aggiorna_banca_dati.py — pipeline di aggiornamento di cassazione-penale-db

Scarica dalla pagina "Giurisprudenza Penale" del sito della Corte di Cassazione
le pronunce segnalate dall'Ufficio del Massimario (sentenze, ordinanze, questioni SU)
e genera le schede Markdown secondo SPEC_SCHEDA.md.

Regole vincolanti (vedi SPEC_SCHEDA.md):
- ogni campo è copiato TESTUALMENTE dalla pagina della Corte; campo assente = null, mai completato;
- il campo "Ricorrente" NON viene estratto (niente dati personali delle parti);
- scheda con campi obbligatori mancanti -> _QUARANTENA/ + LOG_ERRORI.md, mai pubblicata;
- se la fonte non risponde o la struttura è cambiata: si logga e ci si ferma, MAI inventare.

Uso:
  python3 scripts/aggiorna_banca_dati.py [--dry-run] [--force] [--max-schede N]

Pensato per girare nella GitHub Action (.github/workflows/aggiorna.yml).
Dipendenze: requests, beautifulsoup4.
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.cortedicassazione.it"
URL_LISTA = BASE + "/it/giurisprudenza_penale.page"
UA = ("cassazione-penale-db/1.0 "
      "(+https://github.com/Synthos-Logic/cassazione-penale-db; aggiornamento settimanale)")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEG = os.path.join(ROOT, "SEGNALATE")
QUAR = os.path.join(SEG, "_QUARANTENA")
LOG = os.path.join(SEG, "LOG_ERRORI.md")

MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
        "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
SEZ_ROMANO = {"Prima": "I", "Seconda": "II", "Terza": "III", "Quarta": "IV",
              "Quinta": "V", "Sesta": "VI", "Settima": "VII", "Sezioni Unite": "U"}

OGGI = datetime.date.today().isoformat()
ERRORI = []          # righe da appendere a LOG_ERRORI.md
AZIONI = []          # riepilogo finale


# ----------------------------------------------------------------------------- utilità

def log_errore(msg):
    riga = f"- {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} — {msg}"
    ERRORI.append(riga)
    print(f"[ERRORE] {msg}", file=sys.stderr)


def fetch(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    time.sleep(2)  # gentilezza verso il sito della Corte
    return r.text


def data_it(testo):
    """'22 giugno 2026' | '22/06/2026' | '22/06/26' -> 'YYYY-MM-DD' (None se non riconosciuta)."""
    if not testo:
        return None
    t = testo.strip().rstrip(".")
    m = re.match(r"(\d{1,2})\s+([a-zà]+)\s+(\d{4})", t, re.I)
    if m and m.group(2).lower() in MESI:
        return f"{int(m.group(3)):04d}-{MESI[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if m:
        anno = int(m.group(3))
        anno += 2000 if anno < 100 else 0
        return f"{anno:04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def q(v):
    """Valore per il frontmatter: stringa quotata o null."""
    if v is None or v == "":
        return "null"
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace('"', "'") + '"'


def pulisci(testo):
    """Normalizza spazi senza toccare il contenuto."""
    if testo is None:
        return None
    t = re.sub(r"[ \t]+", " ", testo.replace(" ", " "))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() or None


# ----------------------------------------------------------------------------- registro schede esistenti

def leggi_frontmatter(path):
    fm = {}
    try:
        righe = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return fm
    if not righe or righe[0].strip() != "---":
        return fm
    for r in righe[1:]:
        if r.strip() == "---":
            break
        m = re.match(r"(\w+):\s*(.*)", r)
        if m:
            val = m.group(2).strip().strip('"')
            fm[m.group(1)] = None if val in ("null", "") else val
    return fm


def registro_esistenti():
    """Mappa content_id -> (path, frontmatter) e chiavi (tipo,numero,anno) delle schede presenti."""
    per_id, chiavi = {}, set()
    for dirpath, dirnames, filenames in os.walk(SEG):
        dirnames[:] = [d for d in dirnames if d not in ("_QUARANTENA", "RADAR")]
        for f in filenames:
            if not f.endswith(".md") or f in ("INDICE.md", "RASSEGNE.md", "LOG_ERRORI.md"):
                continue
            p = os.path.join(dirpath, f)
            fm = leggi_frontmatter(p)
            cid = fm.get("content_id")
            if cid:
                per_id[cid] = (p, fm)
            n = fm.get("numero") or fm.get("rg")
            if n and fm.get("anno"):
                chiavi.add((fm.get("tipo"), str(n), str(fm.get("anno"))))
    return per_id, chiavi


# ----------------------------------------------------------------------------- parsing lista

def parse_lista(html):
    """Estrae i contentId SZP/QSP dalla pagina lista (i PPR/restituzioni restano fuori)."""
    trovati, visti = [], set()
    for m in re.finditer(r"contentId=(SZP|QSP)(\d+)", html):
        cid = m.group(1) + m.group(2)
        if cid in visti:
            continue
        visti.add(cid)
        pagina = "penale_dettaglio.page" if m.group(1) == "SZP" else "qsp_dettaglio.page"
        trovati.append({"content_id": cid, "kind": m.group(1),
                        "url": f"{BASE}/it/{pagina}?contentId={cid}"})
    return trovati


# ----------------------------------------------------------------------------- parsing dettaglio SZP

def sezione_da_testo(txt):
    m = re.search(r"\b(Prima|Seconda|Terza|Quarta|Quinta|Sesta|Settima)\s+[Ss]ezione\b", txt)
    if m:
        return m.group(1)
    if re.search(r"\bSezioni\s+[Uu]nite\b", txt):
        return "Sezioni Unite"
    return None


def blocco_tra(txt, inizio_pat, fine_pats):
    """Testo tra il marcatore di inizio e il primo dei marcatori di fine."""
    m = re.search(inizio_pat, txt)
    if not m:
        return None
    resto = txt[m.end():]
    fine = len(resto)
    for fp in fine_pats:
        f = re.search(fp, resto)
        if f and f.start() < fine:
            fine = f.start()
    return pulisci(resto[:fine])


def parse_szp(html, cid, url):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    txt = main.get_text("\n")
    txt = re.sub(r"[ \t]+", " ", txt.replace(" ", " "))

    d = {"content_id": cid, "url_scheda": url}

    m = re.search(r"(Sentenza|Ordinanza)\s+Numero:\s*(\d+)\s*,?\s*deposito del\s+([^\n]+)", txt)
    if not m:
        return None, "intestazione numero/deposito non trovata"
    d["tipo"] = m.group(1).lower()
    d["numero"] = int(m.group(2))
    d["data_deposito"] = data_it(m.group(3))
    d["anno"] = int(d["data_deposito"][:4]) if d["data_deposito"] else None

    d["sezione"] = sezione_da_testo(txt)
    mi = re.search(r"Data inserimento:\s*([^\n]+)", txt)
    d["data_inserimento"] = data_it(mi.group(1)) if mi else None
    mm = re.search(r"Materia:\s*([^\n]+)", txt)
    d["materia"] = pulisci(mm.group(1)) if mm else None
    mp = re.search(r"Presidente:\s*([^\n]+)", txt)
    d["presidente"] = pulisci(mp.group(1)) if mp else None
    mr = re.search(r"Relatore:\s*([^\n]+)", txt)
    d["relatore"] = pulisci(mr.group(1)) if mr else None
    mu = re.search(r"Data udienza:\s*([^\n]+)", txt)
    d["data_udienza"] = data_it(mu.group(1)) if mu else None

    d["oggetto"] = blocco_tra(
        txt, r"\bOggetto\b\s*\n",
        [r"Presidente:", r"Relatore:", r"Data udienza:", r"L[’']\s*esito in sintesi", r"Allegat"])
    d["esito"] = blocco_tra(
        txt, r"L[’']\s*esito in sintesi\s*\n",
        [r"\bAllegat[oi]\b", r"Piè di pagina", r"Scarica Documento"])

    d["url_pdf"] = None
    for a in main.find_all("a", href=True):
        if "/resources/cms/documents/" in a["href"] and a["href"].lower().endswith(".pdf"):
            d["url_pdf"] = a["href"] if a["href"].startswith("http") else BASE + a["href"]
            break

    obbligatori = ["tipo", "numero", "anno", "sezione", "materia", "oggetto", "url_pdf"]
    mancanti = [k for k in obbligatori if not d.get(k)]
    return d, (f"campi mancanti: {', '.join(mancanti)}" if mancanti else None)


# ----------------------------------------------------------------------------- parsing dettaglio QSP

def parse_qsp(html, cid, url):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    txt = main.get_text("\n")
    txt = re.sub(r"[ \t]+", " ", txt.replace(" ", " "))

    d = {"content_id": cid, "url_scheda": url, "tipo": "questione-su"}

    m = re.search(r"Questione penale\s+(Pendente|Decisa)\s+del ricorso\s+R\.?G\.?\s*n?\.?\s*"
                  r"(\d+)\s*/\s*(\d+)(?:\s+ud\.\s*([^\n]+))?", txt)
    if not m:
        m = re.search(r"questione penale\s+(Pendente|Decisa)\s+n\.\s*(\d+)\s*/\s*(\d+)", txt, re.I)
    if not m:
        return None, "intestazione R.G./stato non trovata"
    d["stato"] = m.group(1).lower()
    d["rg"] = f"{m.group(2)}/{m.group(3)}"
    d["anno"] = int(m.group(3))
    d["numero"] = int(m.group(2))
    d["data_udienza"] = data_it(m.group(4)) if m.lastindex and m.lastindex >= 4 and m.group(4) else None

    mi = re.search(r"Data inserimento:\s*([^\n]+)", txt)
    d["data_inserimento"] = data_it(mi.group(1)) if mi else None
    mm = re.search(r"Materia:\s*([^\n]+)", txt)
    d["materia"] = pulisci(mm.group(1)) if mm else None   # spesso NON esposta per le QSP -> null
    mr = re.search(r"Relatore:\s*([^\n]+)", txt)
    d["relatore"] = pulisci(mr.group(1)) if mr else None
    mo = re.search(r"Ordinanza di rimessione:\s*([\d/]+)", txt)
    d["ordinanza_rimessione"] = mo.group(1) if mo else None

    # quesito: blocco tra l'intestazione della questione e il primo campo anagrafico.
    # "Riferimenti normativi:" se presente viene scorporato. "Ricorrente:" NON viene estratto.
    blocco = blocco_tra(
        txt, r"Questione penale\s+(?:Pendente|Decisa)[^\n]*\n",
        [r"Ricorrente:", r"Relatore:", r"Data udienza:", r"Riferimenti normativi:\s*Vedi sopra",
         r"Ordinanza di rimessione:", r"\bAllegat[oi]\b"])
    d["quesito"], d["riferimenti_normativi"] = None, None
    if blocco:
        # rimuove eventuali residui dell'intestazione (varianti di a-capo del CMS della Corte)
        residuo = re.compile(r"^(del ricorso\b.*|R\.?G\.?\s*n?\.?\s*\d+/\d+.*|ud\.\s*\S+.*|n\.\s*\d+/\d+.*)$", re.I)
        righe = [r for r in blocco.split("\n")]
        while righe and (not righe[0].strip() or residuo.match(righe[0].strip())):
            righe.pop(0)
        blocco = "\n".join(righe)
        parti = re.split(r"Riferimenti normativi:\s*", blocco, maxsplit=1)
        d["quesito"] = pulisci(parti[0])
        if len(parti) > 1:
            d["riferimenti_normativi"] = pulisci(parti[1])

    d["url_ordinanza_pdf"] = None
    for a in main.find_all("a", href=True):
        if "/resources/cms/documents/" in a["href"] and a["href"].lower().endswith(".pdf"):
            d["url_ordinanza_pdf"] = a["href"] if a["href"].startswith("http") else BASE + a["href"]
            break

    obbligatori = ["stato", "rg", "anno", "quesito"]
    mancanti = [k for k in obbligatori if not d.get(k)]
    return d, (f"campi mancanti: {', '.join(mancanti)}" if mancanti else None)


# ----------------------------------------------------------------------------- generazione schede

def titolo_szp(d):
    sez = SEZ_ROMANO.get(d["sezione"], d["sezione"])
    return f"Cass. pen., Sez. {sez}, n. {d['numero']}/{d['anno']}"


def blockquote(testo):
    """Prefissa ogni riga con '> ' (blockquote Markdown multi-riga)."""
    return "\n> ".join((testo or "").split("\n"))


def scheda_szp(d):
    su = d["sezione"] == "Sezioni Unite"
    nome = f"{'SU' if su else 'Cass'}_{d['numero']}_{d['anno']}.md"
    corpo = f"""---
tipo: {d['tipo']}
sezione: {q(d['sezione'])}
numero: {d['numero']}
anno: {d['anno']}
data_udienza: {d.get('data_udienza') or 'null'}
data_deposito: {d.get('data_deposito') or 'null'}
data_inserimento: {d.get('data_inserimento') or 'null'}
materia: {q(d.get('materia'))}
presidente: {q(d.get('presidente'))}
relatore: {q(d.get('relatore'))}
rv: null
content_id: {q(d['content_id'])}
url_scheda: {q(d['url_scheda'])}
url_pdf: {q(d['url_pdf'])}
fonte: massimario-segnalate
estratto_il: {OGGI}
---

# {titolo_szp(d)}

## Massima ufficiale (Oggetto)

> {blockquote(d['oggetto'])}

## L'esito in sintesi

{d.get('esito') or "*Non pubblicato sulla scheda ufficiale della Corte.*"}

## Fonte autentica

- Scheda ufficiale: {d['url_scheda']}
- PDF del provvedimento: {d['url_pdf']}
"""
    return nome, corpo


def scheda_qsp(d):
    nome = f"QSP_{d['numero']}_{d['anno']}.md"
    stato_txt = "pendente" if d["stato"] == "pendente" else "decisa"
    ud = f", ud. {d['data_udienza']}" if d.get("data_udienza") else ""
    corpo = f"""---
tipo: questione-su
stato: {stato_txt}
rg: {q(d['rg'])}
anno: {d['anno']}
data_udienza: {d.get('data_udienza') or 'null'}
data_inserimento: {d.get('data_inserimento') or 'null'}
materia: {q(d.get('materia'))}
relatore: {q(d.get('relatore'))}
ordinanza_rimessione: {q(d.get('ordinanza_rimessione'))}
url_ordinanza_pdf: {q(d.get('url_ordinanza_pdf'))}
content_id: {q(d['content_id'])}
url_scheda: {q(d['url_scheda'])}
decisa_da: null
fonte: massimario-segnalate
estratto_il: {OGGI}
---

# Questione SU ({stato_txt}) — R.G. {d['rg']}{ud}

## Quesito

> {blockquote(d['quesito'])}

## Riferimenti normativi

{d.get('riferimenti_normativi') or "*Non indicati sulla scheda ufficiale della Corte.*"}

## Fonte autentica

- Scheda ufficiale: {d['url_scheda']}
- Ordinanza di rimessione (PDF): {d.get('url_ordinanza_pdf') or '*non pubblicata*'}

## Nota d'uso difensivo

{"Questione pendente: NON è un precedente citabile come autorità. Utilizzabile solo come segnalazione dell'esistenza di un contrasto rimesso alle Sezioni Unite" + (f" (udienza fissata al {d['data_udienza']})" if d.get('data_udienza') else "") + ", ad es. a sostegno di istanze di rinvio o in subordine nei motivi. Alla decisione, questa scheda sarà aggiornata (`stato: decisa` + rinvio alla scheda della sentenza SU)." if stato_txt == "pendente" else "Questione decisa dalle Sezioni Unite: cercare la scheda della sentenza SU corrispondente nel registro (campo `decisa_da` quando valorizzato)."}
"""
    return nome, corpo


# ----------------------------------------------------------------------------- indici e manifest

def rigenera_indici(dry):
    schede = []
    for dirpath, dirnames, filenames in os.walk(SEG):
        dirnames[:] = [d for d in dirnames if d not in ("_QUARANTENA", "RADAR")]
        for f in sorted(filenames):
            if f.endswith(".md") and f not in ("INDICE.md", "RASSEGNE.md", "LOG_ERRORI.md"):
                p = os.path.join(dirpath, f)
                fm = leggi_frontmatter(p)
                fm["_rel"] = os.path.relpath(p, SEG)
                schede.append(fm)

    def data_ord(fm):
        return fm.get("data_deposito") or fm.get("data_udienza") or fm.get("data_inserimento") or ""
    schede.sort(key=data_ord, reverse=True)

    pron = [s for s in schede if s.get("tipo") in ("sentenza", "ordinanza")]
    qsp = [s for s in schede if s.get("tipo") == "questione-su"]

    righe = ["# INDICE — Pronunce penali segnalate", "",
             f"> Ultimo aggiornamento: {OGGI} · Schede: {len(schede)} "
             f"({len(pron)} sentenze/ordinanze, {len(qsp)} questioni SU)",
             "> Fonte: pagina \"Giurisprudenza Penale\" del sito della Corte Suprema di Cassazione.",
             "", "## Pronunce per materia", ""]
    per_materia = {}
    for s in pron:
        per_materia.setdefault(s.get("materia") or "Materia non indicata dalla Corte", []).append(s)
    for mat in sorted(per_materia):
        righe.append(f"### {mat}\n")
        for s in per_materia[mat]:
            su = s.get("sezione") == "Sezioni Unite"
            etich = f"Cass. {'SU' if su else 'Sez. ' + SEZ_ROMANO.get(s.get('sezione',''), s.get('sezione',''))} n. {s.get('numero')}/{s.get('anno')}"
            righe.append(f"- **{etich}** · dep. {s.get('data_deposito','?')} → [scheda]({s['_rel']})")
        righe.append("")
    righe += ["## Questioni Sezioni Unite", ""]
    if not qsp:
        righe.append("*Nessuna questione in archivio.*")
    for s in qsp:
        stato = (s.get("stato") or "?").upper()
        righe.append(f"- **QSP R.G. {s.get('rg')} · {stato}** · ud. {s.get('data_udienza','?')} → [scheda]({s['_rel']})")
    righe += ["", "## Registro (numero/anno → scheda)", "",
              "| Pronuncia | Tipo | Sezione | Materia | Deposito / Udienza | Scheda |",
              "|---|---|---|---|---|---|"]
    for s in schede:
        if s.get("tipo") == "questione-su":
            rif, dt = f"R.G. {s.get('rg')}", f"ud. {s.get('data_udienza','?')}"
            tipo = f"questione SU ({s.get('stato','?')})"
        else:
            rif, dt, tipo = f"n. {s.get('numero')}/{s.get('anno')}", f"dep. {s.get('data_deposito','?')}", s.get("tipo", "?")
        righe.append(f"| {rif} | {tipo} | {s.get('sezione') or 'Sezioni Unite'} | "
                     f"{s.get('materia') or '—'} | {dt} | `{s['_rel']}` |")

    manifest = {"schema": "cassazione-penale-db/1", "generato_il": OGGI,
                "tipo_fonte": "massimario-segnalate", "totale_schede": len(schede),
                "collezioni": {}}
    for s in schede:
        annodir = s["_rel"].split(os.sep)[0]
        c = manifest["collezioni"].setdefault(annodir, {"schede": 0, "files": []})
        c["schede"] += 1
        c["files"].append(s["_rel"])

    if not dry:
        open(os.path.join(SEG, "INDICE.md"), "w", encoding="utf-8").write("\n".join(righe) + "\n")
        open(os.path.join(SEG, "manifest.json"), "w", encoding="utf-8").write(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return len(schede)


def scrivi_log():
    if not ERRORI:
        return
    testo = open(LOG, encoding="utf-8").read() if os.path.exists(LOG) else ""
    testo = testo.replace("*Nessun errore registrato.*", "").rstrip() + "\n\n" + "\n".join(ERRORI) + "\n"
    open(LOG, "w", encoding="utf-8").write(testo)


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="solo log, nessuna scrittura")
    ap.add_argument("--force", action="store_true", help="rigenera anche le schede già presenti")
    ap.add_argument("--max-schede", type=int, default=40, help="tetto prudenziale per run")
    ap.add_argument("--backfill", action="store_true",
                    help="scarica tutte le pagine dell'archivio (paginazione ?frame3_item=N)")
    ap.add_argument("--max-pagine", type=int, default=40, help="tetto pagine in backfill")
    args = ap.parse_args()

    print(f"== cassazione-penale-db · pipeline {OGGI} · dry_run={args.dry_run} force={args.force} ==")

    per_id, chiavi = registro_esistenti()
    print(f"Schede in archivio: {len(per_id)}")

    pagine = range(1, args.max_pagine + 1) if args.backfill else [1]
    voci, id_visti_lista = [], set()
    for n in pagine:
        url = URL_LISTA if n == 1 else f"{URL_LISTA}?frame3_item={n}"
        try:
            html_lista = fetch(url)
        except Exception as e:
            log_errore(f"pagina lista {n} non raggiungibile: {e}")
            if n == 1:
                scrivi_log() if not args.dry_run else None
                sys.exit(1)
            break  # errore su pagina successiva: si procede con quanto raccolto
        v = [x for x in parse_lista(html_lista) if x["content_id"] not in id_visti_lista]
        if not v:
            print(f"pagina {n}: nessuna voce nuova — fine archivio")
            break
        id_visti_lista |= {x["content_id"] for x in v}
        voci += v
        if args.backfill:
            print(f"pagina {n}: +{len(v)} voci (totale {len(voci)})")
    if not voci:
        log_errore("nessun contentId SZP/QSP trovato nella pagina lista: struttura cambiata?")
        scrivi_log() if not args.dry_run else None
        sys.exit(1)
    print(f"Pronunce sulla pagina lista: {len(voci)} "
          f"(SZP: {sum(1 for v in voci if v['kind']=='SZP')}, QSP: {sum(1 for v in voci if v['kind']=='QSP')})")

    nuove, aggiornate, saltate, quarantena = 0, 0, 0, 0
    for v in voci[: args.max_schede]:
        cid = v["content_id"]
        esistente = per_id.get(cid)

        # ri-verifica delle QSP pendenti già in archivio (pendente -> decisa)
        ricontrolla_qsp = (esistente and v["kind"] == "QSP"
                           and esistente[1].get("stato") == "pendente")
        if esistente and not args.force and not ricontrolla_qsp:
            saltate += 1
            continue

        try:
            html = fetch(v["url"])
        except Exception as e:
            log_errore(f"{cid}: dettaglio non raggiungibile: {e}")
            continue

        d, problema = (parse_szp if v["kind"] == "SZP" else parse_qsp)(html, cid, v["url"])
        if d is None:
            log_errore(f"{cid}: parsing fallito — {problema}")
            quarantena += 1
            continue
        if problema:
            log_errore(f"{cid}: scheda in quarantena — {problema}")
            if not args.dry_run:
                os.makedirs(QUAR, exist_ok=True)
                open(os.path.join(QUAR, cid + ".json"), "w", encoding="utf-8").write(
                    json.dumps(d, ensure_ascii=False, indent=2))
            quarantena += 1
            continue

        nome, corpo = (scheda_szp if v["kind"] == "SZP" else scheda_qsp)(d)
        anno_dir = os.path.join(SEG, str(d["anno"]))
        dest = os.path.join(anno_dir, nome)

        if ricontrolla_qsp and d.get("stato") == "pendente" and not args.force:
            saltate += 1
            continue  # ancora pendente, nulla da fare

        az = "AGGIORNATA" if esistente else "NUOVA"
        if esistente:
            aggiornate += 1
        else:
            nuove += 1
        AZIONI.append(f"[{az}] {dest.replace(ROOT + os.sep, '')} "
                      f"({d.get('materia') or 'materia non indicata'})")
        print(AZIONI[-1])
        if not args.dry_run:
            os.makedirs(anno_dir, exist_ok=True)
            open(dest, "w", encoding="utf-8").write(corpo)
            # se il file esistente aveva un nome diverso (es. QSP con suffissi legacy), non si rinomina mai

    tot = rigenera_indici(args.dry_run)
    if not args.dry_run:
        scrivi_log()

    print(f"\n== RIEPILOGO ==\nnuove: {nuove} | aggiornate: {aggiornate} | "
          f"saltate (già presenti): {saltate} | in quarantena: {quarantena} | "
          f"errori loggati: {len(ERRORI)} | schede totali in archivio: {tot}")
    if args.dry_run:
        print("(dry-run: nessun file scritto)")


if __name__ == "__main__":
    main()

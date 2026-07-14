#!/usr/bin/env python3
"""
annuario.py — Flag "Annuario" sulle schede CONSULTA (cassazione-penale-db)

La Corte costituzionale pubblica ogni anno un Annuario con la rassegna
tematica delle decisioni più rilevanti dell'anno
(cortecostituzionale.it/annuarioYYYY/decisioni-YYYY.html, disponibile dal 2021).

Questo script NON copia il testo redazionale dell'Annuario (non coperto dalla
licenza CC BY-SA degli open data): estrae solo FATTI — numero della pronuncia
e voce tematica sotto cui la Corte l'ha classificata — e li applica come campi
frontmatter (`annuario:` e `tema_annuario:`) alle schede CONSULTA esistenti.

Regole:
- si accettano solo pronunce dell'anno dell'Annuario (i richiami ad anni
  diversi sono precedenti citati, non selezione dell'anno);
- sezioni di servizio escluse (es. "Sentenze e comunicati citati", "Leggi anche");
- idempotente: rieseguito ogni settimana DOPO consulta.py, riapplica i flag
  anche alle schede appena rigenerate (consulta.py li preserva comunque);
- in caso di anomalia: log, mai contenuti inventati.

Uso: python3 scripts/annuario.py [--dry-run] [--da-anno 2021]
Dipendenze: requests, beautifulsoup4.
"""
import argparse
import datetime
import glob
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONS = os.path.join(ROOT, "CONSULTA")
LOG = os.path.join(ROOT, "SEGNALATE", "LOG_ERRORI.md")

URL = "https://www.cortecostituzionale.it/annuario{anno}/decisioni-{anno}.html"
UA = ("cassazione-penale-db/1.0 annuario "
      "(+https://github.com/Synthos-Logic/cassazione-penale-db)")
PRIMO_ANNUARIO = 2021  # prima edizione online dell'Annuario

# Sezioni dell'Annuario che NON classificano decisioni dell'anno
TEMI_ESCLUSI = {"sentenze e comunicati citati", "leggi anche", "servizio studi"}

OGGI = datetime.date.today().isoformat()
ERRORI = []


def log_err(msg):
    ERRORI.append(f"- {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — [annuario] {msg}")
    print(f"[annuario][ERRORE] {msg}", file=sys.stderr)


def normalizza(t):
    """Spazi/nbsp collassati, trattini uniformati, maiuscole della Corte rispettate."""
    t = (t or "").replace(" ", " ").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip(" -")


def estrai_riferimento(href):
    """(anno, numero) da un link a una pronuncia, nei tre formati usati dagli
    Annuari: /scheda-pronuncia/AAAA/N (2025+), param_ecli=ECLI:IT:COST:AAAA:N
    (2022-2024), actionSchedaPronuncia.do?anno=AAAA&numero=N (2021-2022)."""
    m = re.search(r"/scheda-pronuncia/(\d{4})/(\d+)", href)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"ECLI:IT:COST:(\d{4}):(\d+)", href, re.I)
    if m:
        return m.group(1), m.group(2)
    if "actionSchedaPronuncia" in href:
        ma = re.search(r"[?&]anno=(\d{4})", href)
        mn = re.search(r"[?&]numero=(\d+)", href)
        if ma and mn:
            return ma.group(1), mn.group(1)
    return None


def scarica_annuario(anno):
    """HTML dell'Annuario di un anno, o None (assente) / '' (irraggiungibile).
    Il sito della Corte usa Radware Bot Manager: a richieste ravvicinate
    risponde 200 ma redirige alla pagina di challenge (validate.perfdrive.com)
    — verificato 14/7/2026. Si rileva e si ritenta con backoff."""
    for tentativo in range(1, 5):
        try:
            r = requests.get(URL.format(anno=anno), headers={"User-Agent": UA}, timeout=60)
        except Exception as e:
            log_err(f"annuario {anno}: fetch fallito: {e}")
            return ""
        if r.status_code == 404:
            return None
        if r.status_code == 200 and "perfdrive" not in r.url and b"<h5" in r.content:
            return r.content
        print(f"[annuario {anno}] challenge anti-bot o pagina anomala "
              f"(HTTP {r.status_code}), ritento ({tentativo}/4)...")
        time.sleep(4 * tentativo)
    log_err(f"annuario {anno}: solo challenge anti-bot dopo 4 tentativi")
    return ""


def leggi_annuario(anno):
    """{(anno, numero) -> tema} per l'Annuario di un anno; None se non esiste."""
    html = scarica_annuario(anno)
    if html is None:
        return None
    if not html:
        return {}
    # bytes, non testo: il server non dichiara il charset e requests
    # ripiegherebbe su Latin-1; BeautifulSoup lo rileva dal meta della pagina.
    soup = BeautifulSoup(html, "html.parser")
    voci, tema = {}, None
    for el in soup.find_all(["h5", "a"]):
        if el.name == "h5":
            t = normalizza(el.get_text())
            tema = None if (not t or t.casefold() in TEMI_ESCLUSI) else t
            continue
        if tema is None:
            continue
        rif = estrai_riferimento(el.get("href") or "")
        if not rif:
            continue
        a, n = rif
        if int(a) != anno:  # precedente citato, non selezione dell'anno
            continue
        voci.setdefault((a, n), tema)  # prima classificazione vince
    if not voci:
        log_err(f"annuario {anno}: pagina letta ma nessuna decisione estratta (struttura cambiata?)")
    return voci


def applica(anno_pagina, voci, dry):
    """Scrive/aggiorna i campi annuario nel frontmatter delle schede. Ritorna
    (applicate, invariate, mancanti)."""
    applicate, invariate, mancanti = 0, 0, []
    for (anno, numero), tema in sorted(voci.items(), key=lambda kv: int(kv[0][1])):
        trovati = glob.glob(os.path.join(CONS, anno, f"[SO]_{numero}_{anno}.md"))
        if not trovati:
            mancanti.append(f"{numero}/{anno}")
            continue
        path = trovati[0]
        testo = open(path, encoding="utf-8").read()
        tema_q = tema.replace('"', "'")
        blocco = f'annuario: {anno_pagina}\ntema_annuario: "{tema_q}"'
        if re.search(r"^annuario: ", testo, re.M):
            nuovo = re.sub(r"^annuario: .*\ntema_annuario: .*$", lambda m: blocco,
                           testo, count=1, flags=re.M)
        else:
            nuovo, k = re.subn(r"^(n_massime: \d+)$", lambda m: m.group(1) + "\n" + blocco,
                               testo, count=1, flags=re.M)
            if not k:
                log_err(f"scheda {os.path.basename(path)}: frontmatter senza n_massime, flag non applicato")
                continue
        if nuovo == testo:
            invariate += 1
            continue
        if not dry:
            open(path, "w", encoding="utf-8").write(nuovo)
        applicate += 1
        print(f"[ANNUARIO {anno_pagina}] {os.path.relpath(path, ROOT)} — {tema}")
    if mancanti:
        # informativo: pronunce dell'Annuario non (ancora) nell'archivio open data
        print(f"[annuario {anno_pagina}] senza scheda in archivio: {', '.join(mancanti)}")
    return applicate, invariate, mancanti


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--da-anno", type=int, default=PRIMO_ANNUARIO)
    args = ap.parse_args()
    print(f"== annuario Corte costituzionale · {OGGI} · dry_run={args.dry_run} ==")

    tot_app, tot_inv = 0, 0
    for anno in range(args.da_anno, datetime.date.today().year + 1):
        if anno > args.da_anno:
            time.sleep(3)  # non stuzzicare il bot manager
        voci = leggi_annuario(anno)
        if voci is None:
            print(f"[annuario {anno}] non (ancora) pubblicato")
            continue
        if not voci:
            continue  # già loggato
        a, i, _ = applica(anno, voci, args.dry_run)
        print(f"[annuario {anno}] decisioni classificate: {len(voci)} · flag applicati: {a} · già presenti: {i}")
        tot_app += a
        tot_inv += i

    if tot_app and not args.dry_run:
        try:
            from consulta import _rigenera_indice
            _rigenera_indice()
        except Exception as e:
            log_err(f"rigenerazione indice fallita: {e}")
    if ERRORI and not args.dry_run and os.path.exists(LOG):
        t = open(LOG, encoding="utf-8").read().replace("*Nessun errore registrato.*", "").rstrip()
        open(LOG, "w", encoding="utf-8").write(t + "\n\n" + "\n".join(ERRORI) + "\n")
    print(f"\n== ANNUARIO: flag applicati {tot_app} | invariati {tot_inv} | errori {len(ERRORI)} ==")
    if args.dry_run:
        print("(dry-run: nessun file scritto)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
consulta.py — Fonte Corte Costituzionale (cassazione-penale-db)

Consuma il servizio OPEN DATA ufficiale della Corte costituzionale
(dati.cortecostituzionale.it, licenza CC BY-SA 3.0, aggiornamento settimanale):
  - archivio PRONUNCE (testata + dispositivo)
  - archivio MASSIME (massime ufficiali + parametri normativi strutturati)

Genera schede Markdown in CONSULTA/<anno>/ per le pronunce dal --da-anno in poi.

Regole (SPEC_SCHEDA.md, adattate):
- solo campi pubblicati dalla Corte, testuali; campo assente = null;
- NIENTE epigrafe né testo integrale nelle schede (contengono i nomi delle parti
  dei giudizi a quo): testata, dispositivo, massime e parametri, più link ufficiale;
- dedup per (tipo, numero, anno); una scheda esistente viene rigenerata solo se
  cambia il numero di massime disponibili (le massime arrivano dopo la pronuncia);
- in caso di anomalia: log, mai contenuti inventati.

Uso: python3 scripts/consulta.py [--dry-run] [--da-anno 2024] [--force]
Dipendenze: requests (XML: ElementTree stdlib).
"""
import argparse
import datetime
import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONS = os.path.join(ROOT, "CONSULTA")
LOG = os.path.join(ROOT, "SEGNALATE", "LOG_ERRORI.md")

URL_PRONUNCE = "https://dati.cortecostituzionale.it/opendata/distribuzione/CC_OpenPronunce_2001_oggi.zip"
URL_MASSIME = "https://dati.cortecostituzionale.it/opendata/distribuzione/CC_OpenMassime_2001_oggi.zip"
UA = ("cassazione-penale-db/1.0 consulta "
      "(+https://github.com/Synthos-Logic/cassazione-penale-db; open data CC BY-SA 3.0)")

OGGI = datetime.date.today().isoformat()
ERRORI = []


def log_err(msg):
    ERRORI.append(f"- {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — [consulta] {msg}")
    print(f"[consulta][ERRORE] {msg}", file=sys.stderr)


def scarica_zip(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=300)
    r.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(r.content))


def data_iso(t):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (t or "").strip())
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def q(v):
    if v is None or v == "":
        return "null"
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace('"', "'").strip() + '"'


def testo_el(el, tag):
    t = el.findtext(tag)
    return t.strip() if t and t.strip() else None


def itera_pronunce(zf, root_tag_hint, da_anno):
    """Itera gli elementi <pronuncia>. Gli open data della Consulta sono zip ANNIDATI:
    lo zip esterno contiene uno zip per anno (Cc_OpenData_*_YYYY.zip) con dentro l'XML.
    Il filtro per anno avviene già sul nome del file interno (grande risparmio)."""
    for nome in zf.namelist():
        if nome.endswith("/"):
            continue
        m = re.search(r"(\d{4})", os.path.basename(nome))
        if m and int(m.group(1)) < da_anno:
            continue
        try:
            dati = zf.open(nome).read()
        except Exception as e:
            log_err(f"lettura {nome} fallita: {e}")
            continue
        if dati[:2] == b"PK":  # zip annidato
            try:
                interno = zipfile.ZipFile(io.BytesIO(dati))
                sorgenti = [(n, interno.read(n)) for n in interno.namelist() if not n.endswith("/")]
            except Exception as e:
                log_err(f"zip annidato {nome} illeggibile: {e}")
                continue
        else:
            sorgenti = [(nome, dati)]
        for n2, contenuto in sorgenti:
            try:
                for _, el in ET.iterparse(io.BytesIO(contenuto)):
                    if el.tag == "pronuncia":
                        anno = testo_el(el, "pronuncia_testata/anno_pronuncia")
                        if anno and int(anno) >= da_anno:
                            yield el
                        el.clear()
            except ET.ParseError as e:
                log_err(f"XML malformato in {n2}: {e}")


def parametro_str(p):
    """Rende un <parametro> in forma compatta: 'legge 87 del 11/03/1953, art. 23, c. 2'."""
    parti = []
    d = testo_el(p, "descrizione")
    n = testo_el(p, "numero")
    dt = testo_el(p, "data")
    art = testo_el(p, "articolo")
    sa = testo_el(p, "specificazione_articolo")
    c = testo_el(p, "comma")
    sc = testo_el(p, "specificazione_comma")
    if d:
        parti.append(d + (f" {n}" if n else "") + (f" del {dt}" if dt else ""))
    if art:
        parti.append(f"art. {art}" + (f" {sa}" if sa else ""))
    if c:
        parti.append(f"c. {c}" + (f" {sc}" if sc else ""))
    return ", ".join(parti)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--da-anno", type=int, default=1956)  # archivio completo della Consulta
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-schede", type=int, default=25000)
    args = ap.parse_args()

    print(f"== consulta open data · {OGGI} · dry_run={args.dry_run} da_anno={args.da_anno} ==")

    # ------------------------------------------------ download open data
    try:
        zp = scarica_zip(URL_PRONUNCE)
        print(f"[consulta] pronunce: zip scaricato ({len(zp.namelist())} file)")
    except Exception as e:
        log_err(f"download pronunce fallito: {e}")
        _flush_log(args.dry_run)
        sys.exit(1)
    try:
        zm = scarica_zip(URL_MASSIME)
        print(f"[consulta] massime: zip scaricato ({len(zm.namelist())} file)")
    except Exception as e:
        log_err(f"download massime fallito: {e} — si procede senza massime")
        zm = None

    # ------------------------------------------------ indice massime per pronuncia
    massime = {}  # (anno, numero, tipo) -> [ {titolo, testo, parametri[]} ]
    if zm is not None:
        for el in itera_pronunce(zm, "corte_costituzionale_archiviomassime", args.da_anno):
            chiave = (testo_el(el, "pronuncia_testata/anno_pronuncia"),
                      testo_el(el, "pronuncia_testata/numero_pronuncia"),
                      testo_el(el, "pronuncia_testata/tipologia_pronuncia"))
            lst = massime.setdefault(chiave, {"giudizio": testo_el(el, "pronuncia_testata/tipologia_giudizio"),
                                              "voci": []})
            for m in el.iter("massima"):
                lst["voci"].append({
                    "titolo": testo_el(m, "titolo"),
                    "testo": testo_el(m, "testo"),
                    "parametri": [parametro_str(p) for p in m.iter("parametro")],
                })
        print(f"[consulta] massime indicizzate per {len(massime)} pronunce (>= {args.da_anno})")

    # ------------------------------------------------ registro esistenti (n. massime in frontmatter)
    esistenti = {}  # (anno, numero, tipo) -> n_massime nella scheda presente
    for dirpath, dirnames, filenames in os.walk(CONS):
        for f in filenames:
            m = re.match(r"([SO])_(\d+)_(\d{4})\.md$", f)
            if not m:
                continue
            testo = open(os.path.join(dirpath, f), encoding="utf-8").read()
            nm = re.search(r"^n_massime:\s*(\d+)", testo, re.M)
            esistenti[(m.group(3), m.group(2), m.group(1))] = int(nm.group(1)) if nm else 0
    print(f"[consulta] schede già in archivio: {len(esistenti)}")

    # ------------------------------------------------ generazione schede
    nuove, aggiornate, saltate = 0, 0, 0
    for el in itera_pronunce(zp, "elenco_pronunce", args.da_anno):
        if nuove + aggiornate >= args.max_schede:
            print("[consulta] raggiunto il tetto --max-schede")
            break
        t = el.find("pronuncia_testata")
        if t is None:
            continue
        anno = testo_el(t, "anno_pronuncia")
        numero = testo_el(t, "numero_pronuncia")
        tipo = testo_el(t, "tipologia_pronuncia")  # S | O
        if not (anno and numero and tipo in ("S", "O")):
            log_err(f"pronuncia con testata incompleta (anno={anno} numero={numero} tipo={tipo})")
            continue
        chiave = (anno, numero, tipo)
        info_m = massime.get(chiave, {"giudizio": None, "voci": []})
        n_m = len(info_m["voci"])

        if chiave in esistenti and not args.force and esistenti[chiave] == n_m:
            saltate += 1
            continue

        disp = testo_el(el, "pronuncia_testo/dispositivo")
        d = {
            "tipo": "sentenza" if tipo == "S" else "ordinanza",
            "sigla": tipo, "numero": int(numero), "anno": int(anno),
            "presidente": testo_el(t, "presidente"),
            "redattore": testo_el(t, "redattore_pronuncia") or testo_el(t, "relatore_pronuncia"),
            "data_decisione": data_iso(testo_el(t, "data_decisione")),
            "data_deposito": data_iso(testo_el(t, "data_deposito")),
            "giudizio": info_m["giudizio"],
            "url_scheda": f"https://www.cortecostituzionale.it/scheda-pronuncia/{anno}/{numero}",
        }

        corpo = [f"""---
tipo: {d['tipo']}
corte: corte-costituzionale
numero: {d['numero']}
anno: {d['anno']}
data_decisione: {d.get('data_decisione') or 'null'}
data_deposito: {d.get('data_deposito') or 'null'}
presidente: {q(d.get('presidente'))}
redattore: {q(d.get('redattore'))}
tipologia_giudizio: {q(d.get('giudizio'))}
n_massime: {n_m}
url_scheda: {q(d['url_scheda'])}
fonte: consulta-opendata
licenza_dati: "CC BY-SA 3.0 — dati.cortecostituzionale.it"
estratto_il: {OGGI}
---

# Corte cost., {'sent.' if tipo == 'S' else 'ord.'} n. {numero}/{anno}
"""]
        if disp:
            corpo.append("## Dispositivo\n\n" + disp.strip() + "\n")
        else:
            corpo.append("## Dispositivo\n\n*Non presente nell'archivio open data.*\n")
        if n_m:
            corpo.append("## Massime ufficiali\n")
            for i, v in enumerate(info_m["voci"], 1):
                corpo.append(f"### Massima {i}" + (f" — {v['titolo']}" if v.get("titolo") else "") + "\n")
                if v.get("testo"):
                    corpo.append("> " + "\n> ".join(v["testo"].split("\n")) + "\n")
                if v.get("parametri"):
                    corpo.append("*Parametri:* " + " · ".join(p for p in v["parametri"] if p) + "\n")
        else:
            corpo.append("## Massime ufficiali\n\n*Non ancora pubblicate nell'archivio open data "
                         "(la scheda sarà aggiornata automaticamente al loro rilascio).*\n")
        corpo.append(f"""## Fonte autentica

- Scheda ufficiale (testo integrale): {d['url_scheda']}
- Open data: https://dati.cortecostituzionale.it/ (licenza CC BY-SA 3.0)
""")

        nome = f"{tipo}_{numero}_{anno}.md"
        dest_dir = os.path.join(CONS, anno)
        az = "AGGIORNATA" if chiave in esistenti else "NUOVA"
        if az == "AGGIORNATA":
            aggiornate += 1
        else:
            nuove += 1
        if nuove + aggiornate <= 15 or az == "AGGIORNATA":
            print(f"[{az}] CONSULTA/{anno}/{nome} (massime: {n_m})")
        if not args.dry_run:
            os.makedirs(dest_dir, exist_ok=True)
            open(os.path.join(dest_dir, nome), "w", encoding="utf-8").write("\n".join(corpo))

    # ------------------------------------------------ indice
    if not args.dry_run:
        _rigenera_indice()
        _flush_log(False)
    print(f"\n== CONSULTA: nuove {nuove} | aggiornate {aggiornate} | saltate {saltate} | errori {len(ERRORI)} ==")
    if args.dry_run:
        print("(dry-run: nessun file scritto)")


def _rigenera_indice():
    righe = ["# INDICE — Pronunce della Corte costituzionale", "",
             f"> Ultimo aggiornamento: {OGGI} · Fonte: open data ufficiale della Corte costituzionale",
             "> (dati.cortecostituzionale.it, licenza CC BY-SA 3.0). Schede senza epigrafe né testo",
             "> integrale (contengono dati delle parti): dispositivo, massime ufficiali e parametri,",
             "> con link alla scheda ufficiale per il testo completo.", ""]
    tot = 0
    for anno in sorted(os.listdir(CONS), reverse=True):
        adir = os.path.join(CONS, anno)
        if not (os.path.isdir(adir) and anno.isdigit()):
            continue
        files = sorted(os.listdir(adir),
                       key=lambda f: int(re.search(r"_(\d+)_", f).group(1)), reverse=True)
        righe.append(f"## {anno} ({len(files)} pronunce)\n")
        for f in files:
            m = re.match(r"([SO])_(\d+)_(\d{4})\.md$", f)
            if not m:
                continue
            testo = open(os.path.join(adir, f), encoding="utf-8").read()
            dep = re.search(r"^data_deposito:\s*(\S+)", testo, re.M)
            nm = re.search(r"^n_massime:\s*(\d+)", testo, re.M)
            disp1 = ""
            md = re.search(r"## Dispositivo\n\n(.+)", testo)
            if md and not md.group(1).startswith("*"):
                disp1 = " — " + md.group(1).strip()[:110]
            righe.append(f"- **{'Sent.' if m.group(1) == 'S' else 'Ord.'} n. {m.group(2)}/{m.group(3)}** · "
                         f"dep. {dep.group(1) if dep else '?'} · massime: {nm.group(1) if nm else 0} → "
                         f"[scheda]({anno}/{f}){disp1}")
            tot += 1
        righe.append("")
    righe[2] = righe[2].replace("· Fonte", f"· Schede: {tot} · Fonte")
    open(os.path.join(CONS, "INDICE_CONSULTA.md"), "w", encoding="utf-8").write("\n".join(righe) + "\n")
    print(f"[consulta] indice rigenerato: {tot} schede")


def _flush_log(dry):
    if ERRORI and not dry and os.path.exists(LOG):
        t = open(LOG, encoding="utf-8").read().replace("*Nessun errore registrato.*", "").rstrip()
        open(LOG, "w", encoding="utf-8").write(t + "\n\n" + "\n".join(ERRORI) + "\n")


if __name__ == "__main__":
    main()
